"""Two workflows on one worker.

SupportAgentWorkflow  - short-lived, one per ticket. Runs the agent.
PromptImproverWorkflow - long-lived. Watches Oodle for an insight, drafts a
                         candidate prompt, gates it, waits for a human, and
                         ships it by moving the `production` label.
"""

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import asyncio
    import json
    import logging
    import os
    import time

    import httpx

    import oodle
    import otel
    import slack
    from agent import generate, llm_turn, run_tool, tool_response
    from google.genai import types
    from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
    from temporalio.client import Client
    from temporalio.contrib.opentelemetry import TracingInterceptor
    from temporalio.exceptions import ActivityError
    from temporalio.worker import Worker
    from tools import TOOLS

SERVICE_NAME = os.environ.get("SERVICE_NAME", "support-agent")
TASK_QUEUE = "self-improving-loop"
PROMPT_NAME = os.environ.get("PROMPT_NAME", "order-support-agent")
MAX_TURNS = 8
POLL_SECONDS = int(os.environ.get("INSIGHT_POLL_SECONDS", "120"))
MAX_ATTEMPTS = int(os.environ.get("IMPROVER_MAX_ATTEMPTS", "3"))
EXPERIMENT_POLLS = 80  # 15s apart: give an experiment 20 minutes
COOLDOWN = timedelta(minutes=int(os.environ.get("IMPROVER_COOLDOWN_MINUTES", "10")))

log = logging.getLogger("self-improving-loop")


# --------------------------------------------------------------------------
# Activities: the agent
# --------------------------------------------------------------------------

@activity.defn
async def resolve_prompt(request: dict) -> dict:
    """Resolve `production` to an integer version, unless the run asks for one.
    An Oodle experiment asks for the candidate's version; a customer never does.

    This is an Activity, deliberately. Workflow code is replayed; resolving a
    label in workflow code would resolve a *different* version on replay the
    moment the improver moves it, which is exactly what this demo does. The
    integer is pinned into Event History and passed to every later Activity.
    """
    resolved = oodle.get_prompt(request["name"], label="production",
                                version=request.get("version"))
    version = resolved["version"]
    otel.prompt_version.set(version)
    log.info("Pinned %s to version %d", request["name"], version)
    return {
        "version": version,
        "prompt": resolved["prompt"],
        "tools": (resolved.get("config") or {}).get("tools") or [],
    }


@activity.defn
async def agent_turn(request: dict) -> dict:
    otel.prompt_version.set(request["prompt_version"])
    try:
        return llm_turn(request["system"], request["tools"], request["history"])
    finally:
        otel.flush_spans()


@activity.defn
async def agent_tool(call: dict) -> dict:
    otel.prompt_version.set(call["prompt_version"])
    try:
        return run_tool(call["name"], call.get("args") or {})
    finally:
        otel.flush_spans()


# --------------------------------------------------------------------------
# Activities: the improver
# --------------------------------------------------------------------------

# The kinds of finding a prompt edit can actually fix. Anything else is a real
# problem but not this workflow's job, and drafting against it wastes a lap.
FIXABLE = ("invalid_args", "tool_error", "wrong_tool_arguments", "redundant_tool_calls")


@activity.defn
async def fetch_insight(request: dict) -> list:
    """Ask Oodle what it found. Nobody wrote a test set: these come from real traffic.

    Takes EVERY fixable finding, not just the loudest. Findings arrive one per tool,
    so drafting from the top one alone would fix `lookup_order`, leave `issue_refund`
    broken, and get the candidate refused by the gate.

    Findings already acted on are skipped. Shipping a fix does not make the finding
    disappear, because it still covers the traffic that caused it, and without this
    the improver would redraft the same prompt every lap."""
    handled = set(request.get("handled") or [])
    ours = [r for r in oodle.recommendations()
            if r.get("service_name") == request["service_name"]]
    fixable = [r for r in ours
               if r.get("category") in FIXABLE and r.get("fingerprint") not in handled]
    picked = sorted(
        fixable,
        key=lambda r: (r.get("severity") == "high", r.get("prevalence", {}).get("affected", 0)),
        reverse=True,
    )[:3]
    for r in picked:
        log.info("Insight: %s", r.get("title"))
    return picked


DRAFT_INSTRUCTIONS = """\
You maintain the system prompt and tool declarations for a customer-support agent.
An observability platform analysed the agent's live traces and raised the findings
below. The evidence shows the exact arguments the agent sent and the exact errors it
got back.

Rewrite the system prompt and the tool declarations so the agent gets these calls right
on the first attempt. Put the real contract - identifier formats, units, allowed enum
values - into the tool parameter descriptions where the model will actually read it.

Fix EVERY finding, and every failure mode visible in the evidence, in one pass. A
candidate that fixes one tool and leaves another broken is rejected outright.

Keep the same tool names and the same parameter names. Do not invent tools.

Reply with JSON only: {"prompt": "<new system prompt>", "tools": [<tool declarations>],
"rationale": "<one sentence>"}
"""


def _valid_tools(candidate, fallback):
    if not isinstance(candidate, list) or not candidate:
        return fallback
    names = {t.get("name") for t in candidate if isinstance(t, dict)}
    if names != set(TOOLS):
        return fallback
    return candidate


@activity.defn
async def draft_candidate(payload: dict) -> dict:
    current = oodle.get_prompt(PROMPT_NAME, label="production")
    current_tools = (current.get("config") or {}).get("tools") or []

    brief = json.dumps({
        "findings": [
            {
                "title": insight.get("title"),
                "description": insight.get("description"),
                "details": insight.get("details"),
                "evidence": [
                    {"tool": e.get("span_name"), "sent": e.get("span_input"),
                     "got": e.get("span_output")}
                    for e in (insight.get("evidence") or [])[:6]
                ],
            }
            for insight in payload["insights"]
        ],
        "current_prompt": current["prompt"],
        "current_tools": current_tools,
    }, indent=2)

    response = generate(
        contents=[{"role": "user", "parts": [{"text": brief}]}],
        config=types.GenerateContentConfig(
            system_instruction=DRAFT_INSTRUCTIONS,
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    drafted = json.loads(response.text)
    return {
        "prompt": drafted.get("prompt") or current["prompt"],
        "tools": _valid_tools(drafted.get("tools"), current_tools),
        "rationale": drafted.get("rationale", ""),
        "baseline_version": current["version"],
    }


DATASET_NAME = os.environ.get("DATASET_NAME", "order-support-eval")
TUNNEL_METRICS_URL = os.environ.get("TUNNEL_METRICS_URL", "http://tunnel:2000")


@activity.defn
async def start_experiment(version: int) -> dict:
    """The gate, part one. Oodle replays the dataset through the REAL agent: its
    experiment runner calls our webhook once per ticket, and each call runs a
    SupportAgentWorkflow pinned to the candidate version named in the run.

    The tunnel's URL changes when it restarts, so point the webhook at it first."""
    host = httpx.get(f"{TUNNEL_METRICS_URL}/quicktunnel", timeout=10).json()["hostname"]
    webhook_id = oodle.upsert_webhook(f"https://{host}/agent")
    evaluator_id = oodle.upsert_evaluator()
    dataset = oodle.dataset(DATASET_NAME)
    run_name = f"prompt-v{version}-{int(time.time())}"
    job = oodle.start_experiment(dataset["id"], webhook_id, run_name, [evaluator_id])
    log.info("Experiment %s queued in Oodle over %s", run_name, DATASET_NAME)
    return {"job_id": job["id"], "run_id": job["datasetRunId"], "run_name": run_name,
            "run_url": oodle.ui_run_url(DATASET_NAME, job["datasetRunId"])}


@activity.defn
async def experiment_result(experiment: dict) -> dict | None:
    """The gate, part two. None while the run is still going. Once it ends, Oodle's
    code evaluator (tool_errors_eval.py) must have scored every ticket
    no_tool_errors = true from the agent's trace, or the label never moves."""
    status = oodle.job(experiment["job_id"])["status"]
    if status in ("pending", "queued", "running", "in_progress"):
        return None
    errors = model_calls = failed = unscored = 0
    items = oodle.run_items(experiment["run_id"])
    for item in items:
        scores = {s["name"]: s["value"] for s in item.get("scores") or []}
        if item.get("status") != "completed" or "no_tool_errors" not in scores:
            unscored += 1  # the webhook call failed, or the evaluator never ran
            continue
        failed += not scores["no_tool_errors"]
        errors += int(scores.get("tool_errors", 0))
        model_calls += int(scores.get("model_calls", 0))
    passed = status == "completed" and items and not unscored and not failed
    log.info("Experiment %s %s: %d of %d tickets had tool errors (%d in all), %d unscored",
             experiment["run_name"], status, failed, len(items), errors, unscored)
    return {**experiment, "passed": bool(passed), "status": status, "tool_errors": errors,
            "failed_items": failed, "unscored_items": unscored, "turns": model_calls,
            "tickets": len(items)}


@activity.defn
async def publish_candidate(candidate: dict) -> int:
    created = oodle.create_prompt(
        PROMPT_NAME,
        candidate["prompt"],
        candidate["tools"],
        labels=["candidate"],
        commit_message=candidate.get("rationale", "drafted from an Oodle finding")[:200],
    )
    log.info("Published candidate version %d (unlabelled for production)", created["version"])
    return created["version"]


TEMPORAL_UI_URL = os.environ.get("TEMPORAL_UI_URL", "http://localhost:8083")


@activity.defn
async def notify_slack(state: dict) -> None:
    """Ask a person to approve, in Slack. The message itself is built in slack.py."""
    info = activity.info()
    workflow_url = (f"{TEMPORAL_UI_URL}/namespaces/{info.workflow_namespace}/workflows/"
                    f"{info.workflow_id}/{info.workflow_run_id}/history")
    if slack.post(slack.approval_message(state, workflow_url)):
        log.info("Asked for approval of version %d in Slack", state["candidate_version"])
    else:
        log.warning("No SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN+SLACK_CHANNEL; skipped Slack")


@activity.defn
async def promote(version: int) -> None:
    oodle.move_label(PROMPT_NAME, version, "production")
    log.info("production -> version %d", version)


# --------------------------------------------------------------------------
# Workflows
# --------------------------------------------------------------------------

@workflow.defn(name="SupportAgentWorkflow")
class SupportAgentWorkflow:
    @workflow.run
    async def run(self, ticket: dict) -> dict:
        resolved = await workflow.execute_activity(
            resolve_prompt,
            {"name": PROMPT_NAME, "version": ticket.get("prompt_version")},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        version = resolved["version"]
        history = [{"role": "user", "parts": [{"text": ticket["text"]}]}]
        tool_errors = 0

        for turn in range(MAX_TURNS):
            step = await workflow.execute_activity(
                agent_turn,
                {
                    "system": resolved["prompt"],
                    "tools": resolved["tools"],
                    "history": history,
                    "prompt_version": version,
                },
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=RetryPolicy(maximum_attempts=3,
                                         non_retryable_error_types=["QuotaExhausted"]),
            )
            history.append(step["model_content"])

            if not step["tool_calls"]:
                return {"ticket": ticket["id"], "reply": step["text"], "prompt_version": version,
                        "turns": turn + 1, "tool_errors": tool_errors}

            for call in step["tool_calls"]:
                result = await workflow.execute_activity(
                    agent_tool,
                    {**call, "prompt_version": version},
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if "error" in result:
                    tool_errors += 1
                history.append(tool_response(call["name"], result))

        return {"ticket": ticket["id"], "reply": None, "prompt_version": version,
                "turns": MAX_TURNS, "tool_errors": tool_errors}


@workflow.defn(name="PromptImproverWorkflow")
class PromptImproverWorkflow:
    def __init__(self):
        self._state = {"status": "watching"}
        self._insight = None
        self._decision = None

    @workflow.signal
    def insight(self, payload: dict) -> None:
        """Where a finding arrives if you push it in rather than wait for the poll."""
        self._insight = payload

    @workflow.signal
    def decide(self, decision: str) -> None:
        self._decision = decision

    @workflow.query
    def state(self) -> dict:
        return self._state

    async def _cool_off(self) -> None:
        """A durable timer, so a failed attempt costs nothing while it waits.
        Cut short if a fresh finding is signalled in."""
        try:
            await workflow.wait_condition(
                lambda: self._insight is not None, timeout=COOLDOWN)
        except asyncio.TimeoutError:
            pass

    @workflow.run
    async def run(self, carried: dict | None = None) -> dict:
        carried = carried or {}
        attempts = carried.get("attempts", 0)
        handled = carried.get("handled") or []
        self._state = {"status": "watching", "attempts": attempts,
                       "handled": len(handled), "previous": carried.get("last")}

        # A finding is still there on the next poll, so a candidate that fails the
        # gate would be redrafted immediately, forever, at roughly fifteen model
        # calls a lap. After MAX_ATTEMPTS, stop and wait to be signalled instead.
        if attempts >= MAX_ATTEMPTS:
            self._state = {"status": "given_up", "attempts": attempts,
                           "previous": carried.get("last")}
            workflow.logger.warning(
                "%d candidates in a row failed the gate. Not drafting again until "
                "signalled; run `make nudge` or fix the tools.", attempts)
            await workflow.wait_condition(lambda: self._insight is not None)
            attempts = 0

        insights = None
        while not insights:
            insights = ([self._insight] if self._insight else None) or (
                await workflow.execute_activity(
                    fetch_insight,
                    {"service_name": SERVICE_NAME, "handled": handled},
                    start_to_close_timeout=timedelta(seconds=60),
                    # Unlimited. This poll is the watcher's heartbeat and it is a
                    # cheap idempotent GET; a DNS blip must not end the workflow.
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=5),
                        maximum_interval=timedelta(seconds=POLL_SECONDS),
                        maximum_attempts=0,
                    ),
                )
            )
            if insights:
                break
            try:
                await workflow.wait_condition(
                    lambda: self._insight is not None, timeout=timedelta(seconds=POLL_SECONDS)
                )
            except asyncio.TimeoutError:
                pass

        titles = [i.get("title") for i in insights]
        fingerprints = [i.get("fingerprint") for i in insights if i.get("fingerprint")]
        self._state = {"status": "drafting", "insights": titles, "attempts": attempts}
        try:
            candidate = await workflow.execute_activity(
                draft_candidate,
                {"insights": insights},
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=2,
                                         non_retryable_error_types=["QuotaExhausted"]),
            )
            # Published before it is tested, because Oodle's experiment calls the agent,
            # and the agent can only load a prompt version that exists. It is labelled
            # `candidate`, never `production`, so no customer sees it.
            version = await workflow.execute_activity(
                publish_candidate,
                candidate,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            experiment = await workflow.execute_activity(
                start_experiment,
                version,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            self._state = {"status": "testing", "insights": titles, "candidate_version": version,
                           "run_url": experiment["run_url"], "attempts": attempts}
            # Waiting on Oodle costs nothing: a durable timer between cheap status reads.
            gate = None
            for _ in range(EXPERIMENT_POLLS):
                await workflow.sleep(timedelta(seconds=15))
                gate = await workflow.execute_activity(
                    experiment_result,
                    experiment,
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=5),
                )
                if gate is not None:
                    break
            if gate is None:
                gate = {**experiment, "passed": False, "status": "timed_out", "tool_errors": 0,
                        "failed_items": 0, "turns": 0, "tickets": 0}
        except ActivityError as exc:
            # A bad draft or a failed experiment is a failed attempt, not the end of
            # the watcher. Back off, then go round again.
            workflow.logger.warning("Improvement attempt failed: %s", exc)
            await self._cool_off()
            workflow.continue_as_new({"attempts": attempts + 1, "handled": handled, "last": {
                "status": "attempt_failed", "error": str(exc), "insights": titles}})

        if not gate["passed"]:
            self._state = {"status": "discarded_by_gate", "insights": titles,
                           "gate": gate, "attempts": attempts}
            workflow.logger.info(
                "Candidate v%d did not pass the Oodle experiment (%s, %d tool errors); the "
                "label does not move. Cooling off %s before redrafting.",
                version, gate["status"], gate["tool_errors"], COOLDOWN)
            await self._cool_off()
            workflow.continue_as_new({"attempts": attempts + 1, "handled": handled,
                                      "last": self._state})

        # Parks on a durable timer at zero compute cost. Kill the worker here:
        # it resumes on the same run, and nothing re-emits.
        self._state = {
            "status": "awaiting_approval",
            "insights": [{"title": i.get("title"), "fingerprint": i.get("fingerprint")}
                         for i in insights],
            "candidate_version": version,
            "baseline_version": candidate["baseline_version"],
            "rationale": candidate["rationale"],
            "gate": gate,
        }
        workflow.logger.info("Awaiting human approval of version %d", version)
        try:
            await workflow.execute_activity(
                notify_slack,
                {**self._state},
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ActivityError as exc:
            # Slack being down must not lose the candidate: the approval page and
            # `make approve` still work.
            workflow.logger.warning("Slack notification failed: %s", exc)
        await workflow.wait_condition(lambda: self._decision is not None)

        if self._decision == "approve":
            await workflow.execute_activity(
                promote,
                version,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            self._state = {"status": "promoted", "production_version": version,
                           "insights": titles, "gate": gate}
        else:
            self._state = {"status": "rejected", "candidate_version": version,
                           "insights": titles}

        # A candidate that got as far as a human resets the attempt counter, whichever
        # way they decided: the loop is working, it is not stuck. Either way these
        # findings are now dealt with, so stop redrafting them.
        workflow.continue_as_new({
            "attempts": 0,
            "handled": (handled + fingerprints)[-50:],
            "last": self._state,
        })


async def main():
    runtime = otel.setup(SERVICE_NAME)
    GoogleGenAiSdkInstrumentor().instrument()

    client_ = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "temporal:7233"),
        interceptors=[TracingInterceptor()],
        runtime=runtime,
    )
    log.info("Worker up on task queue %s", TASK_QUEUE)
    await Worker(
        client_,
        task_queue=TASK_QUEUE,
        workflows=[SupportAgentWorkflow, PromptImproverWorkflow],
        activities=[resolve_prompt, agent_turn, agent_tool, fetch_insight,
                    draft_candidate, publish_candidate, start_experiment, experiment_result,
                    notify_slack,
                    promote],
    ).run()


if __name__ == "__main__":
    asyncio.run(main())

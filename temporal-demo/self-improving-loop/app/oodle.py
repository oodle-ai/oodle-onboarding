"""Thin HTTP client for the parts of Oodle this demo uses: the prompt registry
and the findings it reports. Both authenticate with the same Oodle API key."""

import difflib
import hashlib
import json
import os

import httpx

APP_URL = os.environ.get("OODLE_APP_URL", "https://app.oodle.ai").rstrip("/")
INSTANCE = os.environ["OODLE_INSTANCE"]
API_KEY = os.environ["OODLE_API_KEY"]

_INSTANCE_URL = f"{APP_URL}/v1/api/instance/{INSTANCE}"
_PROMPTS = f"{_INSTANCE_URL}/langfuse/api/public/v2"
_AUTH = ("default", API_KEY)


def get_prompt(name: str, label: str = "production", version: int | None = None) -> dict:
    """Resolve a label (or fetch an exact version). Never call this from workflow code."""
    params = {"version": version} if version is not None else {"label": label}
    r = httpx.get(f"{_PROMPTS}/prompts/{name}", params=params, auth=_AUTH, timeout=30)
    r.raise_for_status()
    return r.json()


def create_prompt(name: str, prompt: str, tools: list, labels: list, commit_message: str) -> dict:
    """Add a version. Tool declarations ride along in the prompt's config."""
    r = httpx.post(
        f"{_PROMPTS}/prompts",
        auth=_AUTH,
        timeout=30,
        json={
            "name": name,
            "type": "text",
            "prompt": prompt,
            "config": {"tools": tools},
            "labels": labels,
            "commitMessage": commit_message,
        },
    )
    r.raise_for_status()
    return r.json()


def move_label(name: str, version: int, label: str = "production") -> dict:
    """Roll out by moving a label. This is the deploy."""
    r = httpx.patch(
        f"{_PROMPTS}/prompts/{name}/versions/{version}",
        auth=_AUTH,
        timeout=30,
        json={"newLabels": [label]},
    )
    r.raise_for_status()
    return r.json()


def recommendations() -> list:
    """What Oodle reported from the live traces, on its own."""
    r = httpx.get(
        f"{_INSTANCE_URL}/genai/recommendations",
        headers={"X-API-KEY": API_KEY},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("recommendations") or []


def prompt_diff(name: str, old: int, new: int) -> str:
    """Unified diff of two versions: the prompt text, then the tool declarations."""
    def lines(v):
        p = get_prompt(name, version=v)
        tools = json.dumps((p.get("config") or {}).get("tools") or [], indent=2)
        return (p["prompt"].rstrip() + "\n\n# tools\n" + tools).splitlines()
    return "\n".join(difflib.unified_diff(
        lines(old), lines(new), f"v{old}", f"v{new}", lineterm="", n=1))


# Deep links into the Oodle UI, for the Slack approval message and the demo UI.
def ui_prompt_url(name: str, version: int) -> str:
    return f"{APP_URL}/genai/prompts/{name}?version={version}"


def ui_insight_url(fingerprint: str | None = None) -> str:
    url = f"{APP_URL}/genai/traces/?tab=insights"
    return f"{url}&insight={fingerprint}" if fingerprint else url


# --------------------------------------------------------------------------
# Experiments: Oodle runs a dataset through OUR agent by calling a webhook.
# --------------------------------------------------------------------------

WEBHOOK_NAME = "support-agent-temporal"
# Shared secret for the webhook, derived so the worker (which registers it) and
# the web process (which checks it) agree without another setting.
WEBHOOK_TOKEN = hashlib.sha256(f"{API_KEY}:experiment-webhook".encode()).hexdigest()[:40]
_PUBLIC = f"{_INSTANCE_URL}/langfuse/api/public"


def _api(method: str, path: str, **kwargs) -> dict:
    kwargs.setdefault("timeout", 60)
    r = httpx.request(method, f"{_PUBLIC}/{path}", auth=_AUTH, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"Oodle {method} {path}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


def upsert_webhook(url: str) -> str:
    """Point the experiment webhook at the agent's current public URL."""
    body = {
        "name": WEBHOOK_NAME,
        "description": "The ShopWorld support agent, run as a Temporal workflow",
        "url": url,
        "headers": {"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
        "timeoutSeconds": 240,
        # The run name carries the prompt version under test, e.g. "prompt-v3-<unix time>".
        "requestTemplate": '{"ticket": {{input}}, "item_id": {{id}}, "run": {{run.name}}}',
        # Only the reply is the output. Correctness is scored from the trace by the
        # code evaluator below, not read out of the reply.
        "outputPath": "reply",
    }
    existing = next((w for w in _api("GET", "webhooks").get("data") or []
                     if w["name"] == WEBHOOK_NAME), None)
    if existing:
        _api("PUT", f"webhooks/{existing['id']}", json=body)
        return existing["id"]
    return _api("POST", "webhooks", json=body)["id"]


EVALUATOR_NAME = "support-agent/no-tool-errors"
_EVALUATOR_SOURCE = os.path.join(os.path.dirname(__file__), "tool_errors_eval.py")


def upsert_evaluator() -> str:
    """Make sure the code evaluator exists with the current source. Returns its id."""
    body = {"name": EVALUATOR_NAME, "type": "code", "sourceCodeLanguage": "python",
            "sourceCode": open(_EVALUATOR_SOURCE).read(),
            "higherIsBetter": True,
            "description": "Scores a run item from the agent's trace: did any tool call fail?"}
    templates = _api("GET", "eval-templates")
    existing = next((t for t in (templates.get("data") if isinstance(templates, dict) else templates)
                     if t.get("name") == EVALUATOR_NAME), None)
    if existing:
        _api("PATCH", f"eval-templates/{existing['id']}", json=body)
        return existing["id"]
    return _api("POST", "eval-templates", json=body)["id"]


def dataset(name: str) -> dict:
    return _api("GET", f"datasets/{name}")


def start_experiment(dataset_id: str, webhook_id: str, run_name: str, evaluator_ids: list) -> dict:
    return _api("POST", "jobs", json={"type": "llm-experiment", "config": {
        "datasetId": dataset_id, "webhookId": webhook_id, "runName": run_name,
        "evaluatorIds": evaluator_ids}})


def job(job_id: str) -> dict:
    return _api("GET", f"jobs/{job_id}")


def run_items(run_id: str) -> list:
    return _api("GET", "dataset-run-items",
                params={"datasetRunId": run_id, "limit": 100}).get("data") or []


def ui_run_url(dataset_name: str, run_id: str) -> str:
    return f"{APP_URL}/genai/datasets/{dataset_name}/runs/{run_id}"

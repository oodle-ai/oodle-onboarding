"""The Slack approval message, in Block Kit.

A card for the ask and the links, a table of what changed field by field, and the
raw diff in a markdown code block. Links, not interactive buttons: interactivity
needs a public URL for Slack to call back, and this demo runs on a laptop.

    python slack.py preview 1 3     post the message for v1 -> v3, no workflow needed
"""

import os
import sys

import httpx
import oodle

PROMPT_NAME = os.environ.get("PROMPT_NAME", "order-support-agent")
TEMPORAL_UI_URL = os.environ.get("TEMPORAL_UI_URL", "http://localhost:8083")
DEMO_UI_URL = os.environ.get("DEMO_UI_URL", "http://localhost:8090")


def _clip(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def field_changes(old: dict, new: dict) -> list:
    """(field, before, after) for everything the model reads: the prompt text,
    each tool description, and each parameter's description and enum."""
    rows = []
    if old["prompt"].strip() != new["prompt"].strip():
        rows.append(("system prompt", old["prompt"], new["prompt"]))

    def tools(p):
        return {t["name"]: t for t in (p.get("config") or {}).get("tools") or []}

    before, after = tools(old), tools(new)
    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name, {}), after.get(name, {})
        if a.get("description") != b.get("description"):
            rows.append((name, a.get("description") or "-", b.get("description") or "-"))
        pa = (a.get("parameters") or {}).get("properties") or {}
        pb = (b.get("parameters") or {}).get("properties") or {}
        for param in sorted(pa.keys() | pb.keys()):
            for key in ("description", "enum"):
                x, y = (pa.get(param) or {}).get(key), (pb.get(param) or {}).get(key)
                if x != y:
                    fmt = lambda v: ", ".join(v) if isinstance(v, list) else (v or "-")
                    label = f"{name}.{param}" + (" (enum)" if key == "enum" else "")
                    rows.append((label, fmt(x), fmt(y)))
    return rows


def _cell(text, **style):
    if not style:
        return {"type": "raw_text", "text": text}
    return {"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": [
        {"type": "text", "text": text, "style": style}]}]}


def approval_message(state: dict, workflow_url: str) -> dict:
    """state is the improver's awaiting_approval state."""
    base, cand = state["baseline_version"], state["candidate_version"]
    old = oodle.get_prompt(PROMPT_NAME, version=base)
    new = oodle.get_prompt(PROMPT_NAME, version=cand)
    gate = state["gate"]
    passed = gate["tool_errors"] == 0

    table = [[_cell("What changed", bold=True), _cell(f"Live v{base}", bold=True),
              _cell(f"Candidate v{cand}", bold=True)]]
    for field, before, after in field_changes(old, new)[:15]:
        table.append([_cell(field, code=True), _cell(_clip(before, 160)),
                      _cell(_clip(after, 240), bold=True)])

    diff = oodle.prompt_diff(PROMPT_NAME, base, cand)
    if len(diff) > 2800:
        diff = diff[:2800] + "\n… (truncated, full diff on the approval page)"

    findings = "\n".join(
        f"• <{oodle.ui_insight_url(i.get('fingerprint'))}|{i.get('title')}>"
        for i in state["insights"])

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "emoji": True,
                                    "text": f":robot_face: Prompt v{cand} is waiting for your approval"}},
        {"type": "card",
         "title": {"type": "mrkdwn", "text": f"*{PROMPT_NAME}*  v{base} → v{cand}"},
         "subtitle": {"type": "mrkdwn", "text": (
             f"{':white_check_mark: Oodle experiment passed' if passed else ':x: Oodle experiment failed'}, "
             f"{gate['tool_errors']} bad tool calls")},
         "body": {"type": "mrkdwn", "text": _clip(state.get("rationale") or "Drafted from an Oodle finding.", 200)},
         "subtext": {"type": "plain_text", "text": (
             f"Oodle replayed {gate['tickets']} tickets through the live agent and scored each "
             f"trace with the no-tool-errors code evaluator ({gate['turns']} model calls)")},
         "actions": [
             {"type": "button", "style": "primary", "url": f"{DEMO_UI_URL}/approval",
              "text": {"type": "plain_text", "text": "Approve"}},
             {"type": "button", "url": gate.get("run_url") or oodle.ui_prompt_url(PROMPT_NAME, cand),
              "text": {"type": "plain_text", "text": "Experiment"}},
             {"type": "button", "url": workflow_url,
              "text": {"type": "plain_text", "text": "Temporal"}},
         ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*What Oodle found*\n{findings}"}},
        {"type": "table", "column_settings": [{"is_wrapped": True}] * 3, "rows": table},
        {"type": "markdown", "text": f"**Full diff v{base} → v{cand}**\n```diff\n{diff}\n```"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": (
            f"<{oodle.ui_prompt_url(PROMPT_NAME, cand)}|Candidate v{cand} in Oodle>  ·  "
            f"<{oodle.ui_prompt_url(PROMPT_NAME, base)}|Live v{base} in Oodle>  ·  "
            f"<{oodle.ui_insight_url()}|All Oodle insights>  ·  "
            f"Approving moves the `production` label. Nothing is redeployed.")}]},
    ]
    text = f"Prompt {PROMPT_NAME} v{cand} is waiting for approval: {DEMO_UI_URL}/approval"
    return {"text": text, "blocks": blocks}


def post(message: dict) -> bool:
    """Send via incoming webhook, or a bot token with chat:write. False if neither is set."""
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    token, channel = os.environ.get("SLACK_BOT_TOKEN"), os.environ.get("SLACK_CHANNEL")
    if webhook:
        r = httpx.post(webhook, json=message, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Slack refused the message: {r.status_code} {r.text}")
    elif token and channel:
        r = httpx.post("https://slack.com/api/chat.postMessage", timeout=30,
                       headers={"Authorization": f"Bearer {token}"},
                       json={"channel": channel, "unfurl_links": False, **message})
        if not r.json().get("ok"):
            raise RuntimeError(f"Slack refused the message: {r.json()}")
    else:
        return False
    return True


if __name__ == "__main__" and sys.argv[1:2] == ["preview"]:
    base, cand = int(sys.argv[2]), int(sys.argv[3])
    state = {"baseline_version": base, "candidate_version": cand,
             "rationale": oodle.get_prompt(PROMPT_NAME, version=cand).get("commitMessage"),
             "gate": {"tool_errors": 0, "tickets": 4, "turns": 12},
             "insights": [{"title": "Wrong tool arguments: lookup_order and issue_refund in support-agent"}]}
    print("posted" if post(approval_message(state, f"{TEMPORAL_UI_URL}/namespaces/default/workflows"))
          else "no Slack configured")

"""mcp-app: the backend that drives the work, the way the reference backend does.

Two paths, both traced with zero-code `opentelemetry-instrument` plus the
Claude SDK's own spans:

POST /api/managedagents/rfpgonogo/create
    Creates a managed agent for this one session, opens a session, mounts
    the bid's files, sends the task, and returns. A poller thread then
    polls the session (retrieve + events.list) until the agent is done,
    in the same trace as the request. The agent reaches the firm's data
    through mcp-web's MCP server, by the public tunnel URL.

POST /api/chatsession/ask
    The in-house chat: a Messages API tool loop that calls mcp-web's MCP
    server over plain HTTP JSON-RPC.

Deliberate gaps, kept so the Oodle side can be tested against them:

- The agent is new for every session, and its name holds the org, a
  random id, a timestamp and the user's email. No two runs share an agent
  name, and no span carries user.id.
- The MCP server name is new for every session too (mcp-ShortId__<id>).
- The chat path's MCP calls are bare `POST` client spans. There is no
  execute_tool span, so Oodle counts no tool calls on that path.
"""

import contextvars
import os
import random
import string
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx
from fastapi import Body, FastAPI, HTTPException
from opentelemetry import trace

import db

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "claude-haiku-4-5")
ENVIRONMENT_ID = os.environ.get("MCP_ENVIRONMENT_ID", "")
MCP_INTERNAL_URL = os.environ.get("MCP_INTERNAL_URL", "http://mcp-web:8000/mcp")
TUNNEL_METRICS_URL = os.environ.get("TUNNEL_METRICS_URL", "http://mcp-tunnel:2000")
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "5"))
SESSION_TIMEOUT_SECONDS = float(os.environ.get("SESSION_TIMEOUT_SECONDS", "900"))
DOCS = Path(__file__).parent / "bid_docs"

SYSTEM = """Proposal assistant for AEC (Architecture, Engineering and Construction)
firms. The firm's past projects, people, bids and documents are reachable
through the MCP tools; always pass the firm's orgid. Files for the current
bid are mounted under /mnt/session/uploads/workspace. Write deliverables to
/mnt/session/outputs."""

TASK = """<summary_for_user>
Write an RFP go/no-go plan for this bid.
</summary_for_user>

Read the bid with identifier {bid_id} for orgid {orgid}.

A bid is a proposal our firm is working on in response to an RFP. Read the
RFP, find comparable past projects and the people who could staff it, and
fill in the go/no-go template. Write the plan to
/mnt/session/outputs/go_no_go_plan.md and summarize the recommendation."""

app = FastAPI()
db.ensure_seeded()


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


claude = anthropic.Anthropic(default_headers=workspace_headers())


def current_trace_id() -> str:
    return f"{trace.get_current_span().get_span_context().trace_id:032x}"


def short_id(n: int = 14) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def public_mcp_url() -> str:
    """The MCP URL Anthropic can reach: MCP_PUBLIC_URL when set, otherwise
    the hostname of cloudflared's quick tunnel."""
    if url := os.environ.get("MCP_PUBLIC_URL"):
        return url
    resp = httpx.get(f"{TUNNEL_METRICS_URL}/quicktunnel", timeout=5)
    resp.raise_for_status()
    hostname = resp.json().get("hostname")
    if not hostname:
        raise HTTPException(503, "the tunnel has no hostname yet; retry in a few seconds")
    return f"https://{hostname}/mcp"


def record_progress(session_id: str, **fields) -> None:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db.session() as conn:
        db.q(conn, f"UPDATE sessions SET {cols} WHERE session_id = ?", (*fields.values(), session_id))


def is_done(events) -> str | None:
    """The stop reason once the agent has finished the task, else None."""
    for event in reversed(events):
        if event.type == "session.status_terminated":
            return "terminated"
        if event.type == "session.status_idle":
            reason = event.stop_reason.type
            return None if reason == "requires_action" else reason
        if event.type in ("session.status_running", "user.message"):
            return None
    return None


def poll_session(session_id: str, agent_id: str) -> None:
    """Poll the session until the agent is done, as the reference backend does:
    retrieve the session, read the newest user message, then read every
    event, on a fixed interval."""
    deadline = time.monotonic() + SESSION_TIMEOUT_SECONDS
    status = "running"
    try:
        while time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            claude.beta.sessions.retrieve(session_id)
            list(claude.beta.sessions.events.list(
                session_id=session_id, order="desc", types=["user.message"], limit=1,
            ))
            events = list(claude.beta.sessions.events.list(session_id=session_id, order="asc"))
            record_progress(session_id, status="running", events=len(events))
            if stop := is_done(events):
                status = stop
                break
        else:
            status = "timeout"
    except Exception as exc:  # the poller must always record an end state
        status = f"error: {type(exc).__name__}"
    finally:
        record_progress(session_id, status=status)
        # The agent belongs to this one session. Archive it so runs do not
        # pile up agents in the org; archiving does not change the trace.
        try:
            claude.beta.agents.archive(agent_id)
        except Exception:
            pass


@app.post("/api/managedagents/rfpgonogo/create")
def create_go_no_go(
    orgid: int = Body(db.DEMO_ORG_ID),
    bidId: str = Body(db.DEMO_BID_ID),
    userEmail: str = Body("estimator@example.com"),
):
    if not ENVIRONMENT_ID:
        raise HTTPException(400, "Set MCP_ENVIRONMENT_ID in .env (run `make mcp-backend-setup`).")
    with db.session() as conn:
        org = db.q(conn, "SELECT * FROM orgs WHERE org_id = ?", (orgid,)).fetchone()
        bid = db.q(conn, "SELECT * FROM bids WHERE bid_id = ?", (bidId,)).fetchone()
    if org is None or bid is None:
        raise HTTPException(404, "unknown org or bid")

    mcp_url = public_mcp_url()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    # Deliberate gap: one agent per session, named after the user, with an
    # MCP server name that is new every time.
    server_name = f"mcp-ShortId__{short_id()}"
    agent = claude.beta.agents.create(
        name=f"{orgid}_{short_id()}_{stamp}_{userEmail}",
        model=MODEL,
        system=SYSTEM,
        mcp_servers=[{"type": "url", "name": server_name, "url": mcp_url}],
        tools=[
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": True, "permission_policy": {"type": "auto"}},
                "configs": [
                    {"name": "web_fetch", "enabled": False},
                    {"name": "web_search", "enabled": False},
                ],
            },
            {
                "type": "mcp_toolset",
                "mcp_server_name": server_name,
                "default_config": {"permission_policy": {"type": "always_allow"}},
            },
        ],
    )
    session = claude.beta.sessions.create(
        agent=agent.id, environment_id=ENVIRONMENT_ID, title=f"go/no-go {bidId}",
    )
    for path, mount in (
        (DOCS / "sample_rfp.md", "/mnt/session/uploads/workspace/rfp_main/sample_rfp.md"),
        (DOCS / "go_no_go_template.md", "/mnt/session/uploads/workspace/template_doc/go_no_go_template.md"),
    ):
        uploaded = claude.beta.files.upload(file=(path.name, path.read_bytes(), "text/markdown"))
        claude.beta.sessions.resources.add(
            session_id=session.id, type="file", file_id=uploaded.id, mount_path=mount,
        )
    with db.session() as conn:
        db.q(
            conn,
            "INSERT INTO sessions VALUES (?, ?, ?, 'running', 0, ?)",
            (session.id, orgid, agent.id, datetime.now(timezone.utc).isoformat()),
        )
    claude.beta.sessions.events.send(
        session_id=session.id,
        events=[{"type": "user.message", "content": [
            {"type": "text", "text": TASK.format(bid_id=bidId, orgid=orgid)},
        ]}],
    )
    # The poller outlives the request but stays in its trace, as the
    # reference backend's does.
    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(poll_session, session.id, agent.id), daemon=True).start()
    return {
        "sessionId": session.id,
        "agentId": agent.id,
        "agentName": agent.name,
        "mcpUrl": mcp_url,
        "traceId": current_trace_id(),
    }


@app.get("/api/managedagents/sessions/read")
def read_session(sessionId: str):
    with db.session() as conn:
        row = db.q(conn, "SELECT * FROM sessions WHERE session_id = ?", (sessionId,)).fetchone()
    if row is None:
        raise HTTPException(404, "unknown session")
    return dict(row)


class RawMCPClient:
    """JSON-RPC over plain HTTP. Deliberate gap: no tool span around the
    call, so each tool call is only an httpx `POST` client span."""

    def __init__(self, url: str):
        self.url = url
        self.http = httpx.Client(timeout=60, headers={"Accept": "application/json, text/event-stream"})
        self.next_id = 0
        resp = self._post("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "mcp-app-chat", "version": "1.0.0"},
        })
        self.http.headers["Mcp-Session-Id"] = resp.headers.get("Mcp-Session-Id", "")
        self.http.post(self.url, json={"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, method: str, params: dict) -> httpx.Response:
        self.next_id += 1
        resp = self.http.post(self.url, json={"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        resp.raise_for_status()
        return resp

    def tools(self) -> list[dict]:
        return self._post("tools/list", {}).json()["result"]["tools"]

    def call(self, name: str, arguments: dict) -> str:
        result = self._post("tools/call", {"name": name, "arguments": arguments}).json()["result"]
        return "".join(c.get("text", "") for c in result["content"])


@app.post("/api/chatsession/ask")
def ask(orgid: int = Body(db.DEMO_ORG_ID), question: str = Body(...)):
    mcp = RawMCPClient(MCP_INTERNAL_URL)
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
        for t in mcp.tools()
    ]
    messages = [{"role": "user", "content": f"orgid={orgid}. {question}"}]
    answer = ""
    for _ in range(6):
        msg = claude.messages.create(
            model=CHAT_MODEL, max_tokens=1024, system=SYSTEM, tools=tools, messages=messages,
        )
        messages.append({"role": "assistant", "content": msg.content})
        calls = [b for b in msg.content if b.type == "tool_use"]
        if not calls:
            answer = "".join(b.text for b in msg.content if b.type == "text")
            break
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": mcp.call(c.name, c.input)}
            for c in calls
        ]})
    return {"answer": answer, "traceId": current_trace_id()}


@app.get("/healthz")
def healthz():
    return {"ok": True}

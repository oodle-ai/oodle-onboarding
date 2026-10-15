"""mcp-web: the firm's MCP server, the way the reference backend serves it.

A hand-written JSON-RPC handler on POST /mcp (Streamable HTTP, JSON
responses only). The tracing is zero-code `opentelemetry-instrument`, as in
the reference backend, with nothing added by hand. That keeps the same blind spots,
on purpose, so the Oodle side can be tested against them:

- The server span is a bare `POST /mcp`. It names no JSON-RPC method, no
  tool, no MCP session id and no request id, so nothing joins it to the
  agent's `anthropic.mcp_tool_use` span.
- A failed tool call answers 500 from a caught exception, so the span has
  `http.response.status_code=500` and no exception event saying why.
- Every request first reads each org's props table, one query per org,
  before it looks at the method.
- GET /mcp answers 405 (no server-to-client stream).

Clients: the managed agent (through the tunnel, as Anthropic's MCP
connector) and mcp-app's in-house chat path (on the compose network).
"""

import json
import os
import uuid

import anthropic
from fastapi import Body, FastAPI, Header
from fastapi.responses import JSONResponse, Response

import db

SEARCH_MODEL = os.environ.get("SEARCH_MODEL", "claude-haiku-4-5")

app = FastAPI()
db.ensure_seeded()


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


claude = anthropic.Anthropic(default_headers=workspace_headers())

TOOLS = [
    {
        "name": "readBid",
        "description": "Read a bid (a proposal in progress): its client, team, due date and the firm's content guidelines.",
        "inputSchema": {
            "type": "object",
            "properties": {"orgid": {"type": "integer"}, "bidId": {"type": "string"}},
            "required": ["orgid", "bidId"],
        },
    },
    {
        "name": "getOrgEntryDetails",
        "description": "Read the firm's name and profile.",
        "inputSchema": {"type": "object", "properties": {"orgid": {"type": "integer"}}, "required": ["orgid"]},
    },
    {
        "name": "getProjectList",
        "description": "List the firm's past projects with their ids.",
        "inputSchema": {"type": "object", "properties": {"orgid": {"type": "integer"}}, "required": ["orgid"]},
    },
    {
        "name": "readProjects",
        "description": "Read the details of past projects by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "orgid": {"type": "integer"},
                "projectIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["orgid", "projectIds"],
        },
    },
    {
        "name": "getEmployeeList",
        "description": "List the firm's people with their roles.",
        "inputSchema": {"type": "object", "properties": {"orgid": {"type": "integer"}}, "required": ["orgid"]},
    },
    {
        "name": "searchDocuments",
        "description": "Search the firm's document snippets (reports, letters, memos).",
        "inputSchema": {
            "type": "object",
            "properties": {"orgid": {"type": "integer"}, "searchTerms": {"type": "string"}},
            "required": ["orgid", "searchTerms"],
        },
    },
]


class UnknownOrg(Exception):
    pass


def load_org_props(conn) -> dict[int, dict[str, str]]:
    """Read every org's props, one query per org, before any method runs."""
    props = {}
    for (org_id,) in db.q(conn, "SELECT org_id FROM orgs").fetchall():
        rows = db.q(conn, f"SELECT key, value FROM org_{org_id}_props").fetchall()
        props[org_id] = {r["key"]: r["value"] for r in rows}
    return props


def require_org(props, orgid) -> int:
    if orgid not in props:
        raise UnknownOrg(f"org {orgid} not found")
    return orgid


def expand_search_terms(terms: str) -> list[str]:
    """Turn the agent's search terms into keywords with a small model call,
    standing in for the embedding call the reference backend's search makes."""
    msg = claude.messages.create(
        model=SEARCH_MODEL,
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": "Give up to five single-word search keywords, comma separated, "
                       f"no other text, for: {terms}",
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return [w.strip().lower() for w in text.split(",") if w.strip()][:5]


def call_tool(conn, props, name: str, args: dict):
    orgid = require_org(props, args.get("orgid"))
    if name == "readBid":
        bid = db.q(
            conn,
            "SELECT * FROM bids WHERE bid_id = ? AND org_id = ?", (args.get("bidId"), orgid)
        ).fetchone()
        if bid is None:
            return {"error": "bid not found"}
        return {
            "bidMetadata": dict(bid) | {"team": json.loads(bid["team"])},
            "contentGuidelines": db.GUIDELINES,
            "rfpFiles": ["/mnt/session/uploads/workspace/rfp_main/sample_rfp.md"],
            "templateFiles": ["/mnt/session/uploads/workspace/template_doc/go_no_go_template.md"],
        }
    if name == "getOrgEntryDetails":
        org = db.q(conn, "SELECT * FROM orgs WHERE org_id = ?", (orgid,)).fetchone()
        return dict(org) | {"props": props[orgid]}
    if name == "getProjectList":
        rows = db.q(conn, "SELECT project_id, name, year FROM projects WHERE org_id = ?", (orgid,))
        return [dict(r) for r in rows]
    if name == "readProjects":
        ids = args.get("projectIds") or []
        marks = ",".join("?" * len(ids)) or "''"
        rows = db.q(
            conn,
            f"SELECT * FROM projects WHERE org_id = ? AND project_id IN ({marks})", (orgid, *ids)
        )
        return [dict(r) for r in rows]
    if name == "getEmployeeList":
        rows = db.q(conn, "SELECT name, role, years FROM employees WHERE org_id = ?", (orgid,))
        return [dict(r) for r in rows]
    if name == "searchDocuments":
        hits = {}
        for word in expand_search_terms(args.get("searchTerms", "")) or [""]:
            for r in db.q(
                conn,
                "SELECT snippet_id, project_id, title, text FROM documents "
                "WHERE org_id = ? AND (lower(text) LIKE ? OR lower(title) LIKE ?)",
                (orgid, f"%{word}%", f"%{word}%"),
            ):
                hits[r["snippet_id"]] = dict(r)
        return list(hits.values())
    raise KeyError(f"unknown tool {name}")


def rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


@app.post("/mcp")
def mcp(
    payload: dict = Body(...),
    mcp_session_id: str | None = Header(default=None),
):
    method = payload.get("method")
    req_id = payload.get("id")
    try:
        with db.session() as conn:
            props = load_org_props(conn)
            if req_id is None:
                # A notification (notifications/initialized and the like).
                return Response(status_code=202)
            if method == "initialize":
                version = payload.get("params", {}).get("protocolVersion", "2025-06-18")
                body = rpc_result(req_id, {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "firm-mcp", "version": "1.0.0"},
                })
                return JSONResponse(body, headers={"Mcp-Session-Id": uuid.uuid4().hex})
            if method == "ping":
                return JSONResponse(rpc_result(req_id, {}))
            if method == "tools/list":
                return JSONResponse(rpc_result(req_id, {"tools": TOOLS}))
            if method == "tools/call":
                params = payload.get("params", {})
                result = call_tool(conn, props, params.get("name"), params.get("arguments") or {})
                return JSONResponse(rpc_result(req_id, {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "isError": False,
                }))
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"no method {method}"}}
            )
    except Exception:
        # Deliberate: answer 500 without letting the exception reach the
        # instrumentation, as the reference backend does. The span then says 500
        # and nothing about the cause.
        return Response(status_code=500)


@app.get("/healthz")
def healthz():
    return {"ok": True}

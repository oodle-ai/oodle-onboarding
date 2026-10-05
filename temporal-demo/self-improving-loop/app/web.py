"""The demo UI: a ShopWorld storefront with a support chat, and an approval page.

    :8090 /           storefront. Each chat message runs one SupportAgentWorkflow.
    :8090 /approval   what the improver is doing, the candidate diff, approve / reject.
    :8091 /agent      the webhook Oodle's experiment runner calls, once per dataset
                      item. Only this port goes through the public tunnel.

Every model call still comes from a click, the same as the CLI.
"""

import asyncio
import os
import re
import time
from pathlib import Path

import oodle
import otel
from aiohttp import web
from opentelemetry import context, propagate
from signal_insight import INSIGHT
from starter import TASK_QUEUE, submit
from temporalio.client import Client
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.exceptions import WorkflowAlreadyStartedError
from tools import ORDERS, TICKETS

PROMPT_NAME = os.environ.get("PROMPT_NAME", "order-support-agent")
IMPROVER_ID = "prompt-improver"
TEMPORAL_UI_URL = os.environ.get("TEMPORAL_UI_URL", "http://localhost:8083")
HERE = Path(__file__).parent

routes = web.RouteTableDef()


def page(name):
    return lambda request: web.FileResponse(HERE / name)


@routes.get("/api/store")
async def store(request):
    live = await asyncio.to_thread(oodle.get_prompt, PROMPT_NAME)
    return web.json_response({"orders": ORDERS, "tickets": TICKETS, "prompt_version": live["version"],
                              "prompt_url": oodle.ui_prompt_url(PROMPT_NAME, live["version"])})


@routes.post("/api/ticket")
async def ticket(request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise web.HTTPBadRequest(text="empty message")
    ticket_id = body.get("id") or f"W-{int(time.time())}"
    result = await submit(request.app["client"], {"id": ticket_id, "text": text})
    return web.json_response(result)


@routes.get("/api/improver")
async def improver(request):
    handle = request.app["client"].get_workflow_handle(IMPROVER_ID)
    try:
        desc = await handle.describe()
    except Exception:
        return web.json_response({"status": "not_started"})
    out = {"status": desc.status.name.lower(),
           "workflow_url": f"{TEMPORAL_UI_URL}/namespaces/default/workflows/"
                           f"{IMPROVER_ID}/{desc.run_id}/history",
           "insights_url": oodle.ui_insight_url()}
    if desc.status.name != "RUNNING":
        return web.json_response(out)
    try:
        out.update(await handle.query("state"))
    except Exception as exc:  # between runs of a continue-as-new
        out["status"] = f"busy ({exc})"
    if out.get("status") == "awaiting_approval":
        old, new = out["baseline_version"], out["candidate_version"]
        out["diff"] = await asyncio.to_thread(oodle.prompt_diff, PROMPT_NAME, old, new)
        out["candidate_url"] = oodle.ui_prompt_url(PROMPT_NAME, new)
        out["baseline_url"] = oodle.ui_prompt_url(PROMPT_NAME, old)
        for i in out["insights"]:
            i["url"] = oodle.ui_insight_url(i.get("fingerprint"))
    return web.json_response(out)


@routes.post("/api/improver/{action}")
async def improver_action(request):
    client, action = request.app["client"], request.match_info["action"]
    handle = client.get_workflow_handle(IMPROVER_ID)
    if action == "start":
        try:
            await client.start_workflow("PromptImproverWorkflow", id=IMPROVER_ID, task_queue=TASK_QUEUE)
        except WorkflowAlreadyStartedError:
            pass
    elif action == "nudge":
        await handle.signal("insight", INSIGHT)
    elif action in ("approve", "reject"):
        await handle.signal("decide", action)
    else:
        raise web.HTTPNotFound()
    return web.json_response({"ok": True})


async def agent_webhook(request):
    """One dataset item from an Oodle experiment. Runs the real agent workflow,
    pinned to the prompt version named in the run, e.g. "prompt-v3-<unix time>"."""
    if request.headers.get("Authorization") != f"Bearer {oodle.WEBHOOK_TOKEN}":
        raise web.HTTPUnauthorized()
    body = await request.json()
    match = re.search(r"prompt-v(\d+)", str(body.get("run") or ""))
    ticket = {"id": str(body.get("item_id") or f"X-{int(time.time())}"), "text": body["ticket"],
              "prompt_version": int(match.group(1)) if match else None,
              "experiment": request.headers.get("X-Oodle-Experiment")}
    # Continue Oodle's trace, so the run item links to every span of this run.
    token = context.attach(propagate.extract(request.headers))
    try:
        result = await submit(request.app["client"], ticket)
    finally:
        context.detach(token)
    if "error" in result:
        return web.json_response(result, status=500)
    return web.json_response(result)


async def main():
    runtime = otel.setup(os.environ.get("STARTER_SERVICE_NAME", "support-agent-gateway"))
    app = web.Application()
    app["client"] = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "temporal:7233"),
        interceptors=[TracingInterceptor()], runtime=runtime)
    app.router.add_get("/", page("store.html"))
    app.router.add_get("/approval", page("approval.html"))
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8090).start()

    hook = web.Application()
    hook["client"] = app["client"]
    hook.router.add_post("/agent", agent_webhook)
    hook_runner = web.AppRunner(hook)
    await hook_runner.setup()
    await web.TCPSite(hook_runner, "0.0.0.0", 8091).start()
    print("Demo UI on http://localhost:8090, experiment webhook on :8091", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

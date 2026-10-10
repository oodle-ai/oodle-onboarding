"""The browser side: one page and a token endpoint.

``POST /api/token`` starts a call. It names a fresh room, mints a token to
join it, and puts an agent dispatch in the token's room configuration, so
the room is created with the agent already sent for. The PII mode the page
asked for travels in that dispatch's metadata, which the agent reads as
``ctx.job.metadata``.

    python web.py
"""

import json
import os
import uuid
from pathlib import Path

from aiohttp import web
from livekit import api

STATIC = Path(__file__).parent / "static"

AGENT_NAME = os.environ.get("AGENT_NAME", "livekit-demo-agent")
# Where the browser reaches LiveKit, which is not where the agent does.
LIVEKIT_PUBLIC_URL = os.environ.get("LIVEKIT_PUBLIC_URL", "ws://localhost:7880")
PII_MODES = ("allow", "withhold")


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


async def token(request: web.Request) -> web.Response:
    body = await request.json() if request.can_read_body else {}
    mode = body.get("pii_mode", "allow")
    if mode not in PII_MODES:
        raise web.HTTPBadRequest(text=f"pii_mode must be one of {', '.join(PII_MODES)}")

    # Pseudonymous ids, in the shape of a CRM's: the call and the contact.
    call_id = uuid.uuid4().hex[:24]
    contact_id = str(uuid.uuid4())
    room = f"web-call-{call_id}"

    dispatch = api.RoomAgentDispatch(
        agent_name=AGENT_NAME,
        metadata=json.dumps({"pii_mode": mode, "call_id": call_id, "contact_id": contact_id}),
    )
    jwt = (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        # The participant identity is traced as lk.pii.participant_identity.
        .with_identity(contact_id)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(api.RoomConfiguration(agents=[dispatch]))
        .to_jwt()
    )

    return web.json_response(
        {
            "url": LIVEKIT_PUBLIC_URL,
            "token": jwt,
            "call_id": call_id,
            "contact_id": contact_id,
            "pii_mode": mode,
        }
    )


def main() -> None:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/api/token", token)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7870")))


if __name__ == "__main__":
    main()

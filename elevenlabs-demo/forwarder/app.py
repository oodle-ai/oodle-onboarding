"""Forward ElevenLabs Agents post-call traces to Oodle.

ElevenLabs sends a post-call webhook of type post_call_transcription_otel
when a conversation ends. Its data.otlp_traces is an OTLP/JSON trace of the
whole conversation. This service checks the webhook signature with the
ElevenLabs SDK and posts the trace to Oodle's OTLP endpoint unchanged.
Oodle maps the elevenlabs.* attributes onto the GenAI conventions at ingest.
"""

import json
import logging
import os

import requests
from elevenlabs import ElevenLabs
from elevenlabs.core.api_error import ApiError
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("forwarder")

OODLE_ENDPOINT = os.getenv("OODLE_OTLP_ENDPOINT") or (
    f"https://{os.environ['OODLE_INSTANCE']}-otlp.collector.oodle.ai"
)
OODLE_TRACES_URL = OODLE_ENDPOINT.rstrip("/") + "/v1/traces"
OODLE_HEADERS = {
    "Content-Type": "application/json",
    "X-OODLE-INSTANCE": os.environ["OODLE_INSTANCE"],
    "X-API-KEY": os.environ["OODLE_API_KEY"],
}

# Verifying a signature needs no API key. The client is only the SDK's
# entry point to construct_event.
elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY", "unused"))
app = FastAPI()


def webhook_secret() -> str:
    # `make webhook` writes the secret to a file that this container
    # mounts, so the secret works without a restart.
    path = os.getenv("ELEVENLABS_WEBHOOK_SECRET_FILE", "/state/webhook_secret")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/elevenlabs/post-call")
async def post_call(request: Request) -> dict:
    body = (await request.body()).decode()
    try:
        event = elevenlabs.webhooks.construct_event(
            rawBody=body,
            sig_header=request.headers.get("elevenlabs-signature", ""),
            secret=webhook_secret(),
        )
    except ApiError as err:
        log.warning("rejected webhook: %s", err.body)
        raise HTTPException(status_code=401, detail="invalid signature")

    kind = event.get("type")
    data = event.get("data") or {}
    if kind != "post_call_transcription_otel":
        # Other post-call events (JSON transcripts, audio) carry no trace.
        log.info("ignored %s for %s", kind, data.get("conversation_id"))
        return {"ignored": kind}

    traces = data.get("otlp_traces") or {}
    spans = sum(
        len(ss.get("spans", []))
        for rs in traces.get("resourceSpans", [])
        for ss in rs.get("scopeSpans", [])
    )
    response = requests.post(
        OODLE_TRACES_URL, headers=OODLE_HEADERS, data=json.dumps(traces), timeout=30
    )
    if response.status_code >= 300:
        # A 5xx makes ElevenLabs retry the delivery (when retries are on
        # for the webhook), so the trace is not lost.
        log.error("Oodle returned %s: %s", response.status_code, response.text[:300])
        raise HTTPException(status_code=502, detail="Oodle rejected the trace")
    log.info("forwarded %d spans for %s", spans, data.get("conversation_id"))
    return {"forwarded_spans": spans}

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["elevenlabs==2.72.0", "requests>=2.32", "python-dotenv>=1.0"]
# ///
"""ElevenLabs Agents demo for Oodle Agent Observability.

  setup             Create the demo agent: a client tool, a webhook tool and a
                    knowledge base used through RAG. The ids go to state/.
  webhook [URL]     Point the agent's post-call webhook (OpenTelemetry format)
                    straight at Oodle, or at the forwarder reachable at URL.
  chat              A short text-only conversation. No audio, lowest cost.
  voice             A real voice call: a synthetic caller speaks to the agent
                    over audio, so the agent runs speech-to-text, the LLM and
                    text-to-speech. Writes the call audio to state/last-call.wav.
  export CONV_ID    Fetch one conversation as OTLP JSON and forward it to Oodle.
  replay FILE       Forward a saved trace again, as a new trace that ends now.
  teardown          Delete the demo agent, its knowledge base and its webhook.

Without a webhook, chat and voice fetch the trace with the GET conversation
API and forward it. With one, the webhook delivers it, and fetching it too
would store every span twice.
"""

import argparse
import array
import json
import os
import random
import secrets
import sys
import threading
import time
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import (
    AudioInterface,
    ClientTools,
    Conversation,
    ConversationInitiationData,
)

ROOT = Path(__file__).resolve().parent.parent
# override=True: a shell that already exports OODLE_INSTANCE or
# OODLE_API_KEY (common on machines that run other Oodle tools) would
# otherwise send this demo's traces to that instance.
load_dotenv(ROOT / ".env", override=True)

STATE_DIR = ROOT / "state"
AGENT_FILE = STATE_DIR / "agent.json"
SECRET_FILE = STATE_DIR / "webhook_secret"

AGENT_NAME = "Oodle demo: Globetrotter travel desk"
LLM = os.getenv("ELEVENLABS_LLM", "gpt-4.1-mini")
EMBEDDING_MODEL = "multilingual_e5_large_instruct"
# A premade voice, available in every workspace, for the synthetic caller.
CALLER_VOICE = os.getenv("CALLER_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
# The caller is identified as a user, so Oodle groups calls by caller.
CALLER_ID = os.getenv("CALLER_ID", "caller-priya-raman")

POLICY = """Globetrotter Travel policy.

Checked baggage: one bag up to 23 kg is included on international bookings.
Each extra bag costs 60 USD. Overweight bags (23 to 32 kg) cost 75 USD.

Changes: a date change costs 50 USD plus any fare difference. Changes are free
within 24 hours of booking.

Cancellations: refundable fares are refunded in full to the original payment
method within 7 business days. Basic fares are not refundable, but the taxes
are refunded on request.
"""

PROMPT = """You are Maya, the voice assistant of Globetrotter Travel.
Help callers with their bookings, travel money and travel policy.

- To look up a booking, ask for the booking reference and call lookup_booking.
- For exchange rates, call get_exchange_rate.
- For baggage, change and cancellation rules, use the knowledge base.

Keep each answer to one or two short sentences. This is a phone call."""

# Bookings that the lookup_booking client tool knows.
BOOKINGS = {
    "GT1234": {
        "passenger": "Priya Raman",
        "route": "SFO to LHR",
        "date": "2026-11-02",
        "fare": "refundable",
        "bags": 1,
    },
    "GT5678": {
        "passenger": "Sam Ortiz",
        "route": "JFK to CDG",
        "date": "2026-12-18",
        "fare": "basic",
        "bags": 0,
    },
}

SCRIPT = [
    "Hi, can you check booking G T 1 2 3 4 for me?",
    "I will be in London. What is the exchange rate from US dollars to British pounds?",
    "How much does an extra checked bag cost?",
    "Great, thanks. That is all. Goodbye!",
]


def client() -> ElevenLabs:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY in .env")
    return ElevenLabs(api_key=key)


def load_state() -> dict:
    if AGENT_FILE.exists():
        return json.loads(AGENT_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    AGENT_FILE.write_text(json.dumps(state, indent=2))


def agent_id() -> str:
    if os.getenv("ELEVENLABS_AGENT_ID"):
        return os.environ["ELEVENLABS_AGENT_ID"]
    if "agent_id" not in load_state():
        sys.exit("No agent yet. Run: make agent")
    return load_state()["agent_id"]


# --- setup ------------------------------------------------------------------


def setup(_args) -> None:
    state = load_state()
    if "agent_id" in state:
        print(f"Agent already exists: {state['agent_id']} (make teardown to start over)")
        return
    el = client()

    document = el.conversational_ai.knowledge_base.documents.create_from_text(
        name="Globetrotter Travel policy", text=POLICY
    )
    # RAG indexing is asynchronous. Wait for the index, or the first
    # conversation answers without retrieval.
    while True:
        index = el.conversational_ai.knowledge_base.document.compute_rag_index(
            document.id, model=EMBEDDING_MODEL
        )
        if index.status == "succeeded":
            break
        if index.status == "failed":
            sys.exit("RAG index failed")
        time.sleep(3)

    agent = el.conversational_ai.agents.create(
        name=AGENT_NAME,
        tags=["oodle-demo"],
        conversation_config={
            "agent": {
                "first_message": "Hi, this is Maya from Globetrotter Travel. How can I help?",
                "language": "en",
                "prompt": {
                    "prompt": PROMPT,
                    "llm": LLM,
                    "temperature": 0.2,
                    "knowledge_base": [
                        {
                            "type": "text",
                            "id": document.id,
                            "name": "Globetrotter Travel policy",
                            "usage_mode": "auto",
                        }
                    ],
                    "rag": {"enabled": True, "embedding_model": EMBEDDING_MODEL},
                    "tools": [
                        {
                            # Runs in this script. ElevenLabs asks the client
                            # to run it and waits for the result.
                            "type": "client",
                            "name": "lookup_booking",
                            "description": "Look up a booking by its reference, for example GT1234.",
                            "expects_response": True,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "booking_ref": {
                                        "type": "string",
                                        "description": "The booking reference, for example GT1234",
                                    }
                                },
                                "required": ["booking_ref"],
                            },
                        },
                        {
                            # Runs on ElevenLabs: it calls the URL itself.
                            "type": "webhook",
                            "name": "get_exchange_rate",
                            "description": "Get the latest exchange rate between two currencies.",
                            "api_schema": {
                                "url": "https://api.frankfurter.dev/v1/latest",
                                "method": "GET",
                                "query_params_schema": {
                                    "properties": {
                                        "base": {
                                            "type": "string",
                                            "description": "Base currency code, for example USD",
                                        },
                                        "symbols": {
                                            "type": "string",
                                            "description": "Target currency code, for example GBP",
                                        },
                                    },
                                    "required": ["base", "symbols"],
                                },
                            },
                        },
                    ],
                },
            },
        },
    )
    save_state({"agent_id": agent.agent_id, "document_id": document.id})
    print(f"Agent: {agent.agent_id}")
    print(f"Talk to it in the browser: https://elevenlabs.io/app/talk-to?agent_id={agent.agent_id}")


def oodle_endpoint() -> str:
    endpoint = os.getenv("OODLE_OTLP_ENDPOINT") or f"https://{os.environ['OODLE_INSTANCE']}-otlp.collector.oodle.ai"
    return endpoint.rstrip("/")


def webhook(args) -> None:
    """Send the agent's post-call traces to Oodle, or to the forwarder.

    Without a URL the webhook goes straight to Oodle, which takes the trace
    out of the webhook's envelope, and carries the Oodle headers itself.
    With a URL it goes to the forwarder there, which checks the signature
    and forwards the trace.
    """
    el = client()
    state = load_state()
    if "agent_id" not in state:
        sys.exit("No agent yet. Run: make agent")
    settings = {"auth_type": "hmac", "name": "Oodle Agent Observability"}
    if args.url:
        settings["webhook_url"] = args.url.rstrip("/") + "/elevenlabs/post-call"
    else:
        settings["webhook_url"] = oodle_endpoint() + "/v1/otlp/traces/elevenlabs"
        settings["request_headers"] = {
            "X-API-KEY": os.environ["OODLE_API_KEY"],
            "X-OODLE-INSTANCE": os.environ["OODLE_INSTANCE"],
        }
    created = el.webhooks.create(settings=settings)
    # Retries are off on a new webhook. Without them a failed delivery
    # loses the call.
    el.webhooks.update(
        created.webhook_id, name=settings["name"], is_disabled=False, retry_enabled=True
    )
    STATE_DIR.mkdir(exist_ok=True)
    SECRET_FILE.write_text(created.webhook_secret)
    SECRET_FILE.chmod(0o600)
    # Per agent, not workspace wide, so other agents in the workspace keep
    # their own webhook settings.
    el.conversational_ai.agents.update(
        state["agent_id"],
        platform_settings={
            "workspace_overrides": {
                "webhooks": {
                    "post_call_webhook_id": created.webhook_id,
                    "events": ["transcript"],
                    "transcript_format": "opentelemetry",
                }
            }
        },
    )
    # Replace the webhook this demo made before (a quick tunnel gets a new
    # URL each time it starts). ElevenLabs refuses to delete a webhook an
    # agent still uses, so this comes after the agent has the new one.
    if state.get("webhook_id"):
        el.webhooks.delete(state["webhook_id"])
    state["webhook_id"] = created.webhook_id
    save_state(state)
    print(f"Post-call webhook {created.webhook_id} -> {settings['webhook_url']}")


# --- conversations ------------------------------------------------------------


def lookup_booking(params: dict) -> str:
    ref = "".join(str(params.get("booking_ref", "")).upper().split())
    booking = BOOKINGS.get(ref)
    if booking is None:
        return json.dumps({"error": f"No booking found for {ref}"})
    return json.dumps({"booking_ref": ref, **booking})


def client_tools() -> ClientTools:
    tools = ClientTools()
    tools.register("lookup_booking", lookup_booking)
    return tools


def chat(args) -> None:
    replied = threading.Event()

    def on_agent(text: str) -> None:
        print(f"Agent: {text}")
        replied.set()

    conversation = Conversation(
        client=client(),
        agent_id=agent_id(),
        user_id=CALLER_ID,
        requires_auth=True,
        client_tools=client_tools(),
        callback_agent_response=on_agent,
        # Text only: no microphone, speakers or speech services. The trace
        # has the same shape as a call's.
        config=ConversationInitiationData(
            conversation_config_override={"conversation": {"text_only": True}},
        ),
    )
    conversation.start_session()
    replied.wait(timeout=20)
    for message in SCRIPT:
        replied.clear()
        print(f"User:  {message}")
        conversation.send_user_message(message)
        replied.wait(timeout=60)
        # Let a tool call and the turn after it finish first.
        time.sleep(2)
    conversation.end_session()
    finish(conversation.wait_for_session_end(), args)


SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
CHUNK_BYTES = 8000  # 250 ms of 16-bit mono PCM, the size the SDK suggests


class SyntheticCaller(AudioInterface):
    """A caller that speaks the script over the call's audio.

    The SDK calls start() with a callback for microphone audio and output()
    with the agent's speech. This sends the script's lines as speech, made
    with ElevenLabs text to speech, and silence between them, in real time.
    It speaks the next line when the agent has answered and has finished
    speaking. Both sides of the call are kept for a WAV file.
    """

    def __init__(self, lines: list[bytes]):
        self.lines = list(lines)
        self.answered = threading.Event()
        self.answered.set()  # the greeting comes first
        self.done = threading.Event()
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.started_at = 0.0
        self.agent_until = 0.0  # call time at which the agent stops speaking
        self.timeline = array.array("h")

    def _mix(self, at_seconds: float, pcm: bytes) -> None:
        samples = array.array("h", pcm)
        start = int(at_seconds * SAMPLE_RATE)
        with self.lock:
            if len(self.timeline) < start + len(samples):
                self.timeline.extend([0] * (start + len(samples) - len(self.timeline)))
            for i, s in enumerate(samples):
                v = self.timeline[start + i] + s
                self.timeline[start + i] = max(-32768, min(32767, v))

    def now(self) -> float:
        return time.monotonic() - self.started_at

    def start(self, input_callback):
        self.started_at = time.monotonic()
        threading.Thread(target=self._speak, args=(input_callback,), daemon=True).start()

    def _speak(self, send):
        silence = b"\x00" * CHUNK_BYTES
        pending = b""
        while not self.stopped.is_set():
            # The agent's reply can pause mid-sentence (a tool call, the
            # next sentence still generating). Wait long enough that the
            # caller does not cut in, which ElevenLabs would record as an
            # interruption.
            if not pending and self.lines and self.answered.is_set() and self.now() > self.agent_until + 2.5:
                self.answered.clear()
                pending = self.lines.pop(0)
                self._mix(self.now(), pending)
            if not pending and not self.lines and self.answered.is_set() and self.now() > self.agent_until + 3.0:
                self.done.set()
            chunk, pending = pending[:CHUNK_BYTES], pending[CHUNK_BYTES:]
            chunk = chunk.ljust(CHUNK_BYTES, b"\x00") if chunk else silence
            send(chunk)
            time.sleep(CHUNK_BYTES / BYTES_PER_SECOND)

    def output(self, audio: bytes):
        # The agent's speech arrives faster than real time. Place it after
        # what is already queued, the way a speaker would play it.
        start = max(self.now(), self.agent_until)
        self._mix(start, audio)
        self.agent_until = start + len(audio) / BYTES_PER_SECOND

    def interrupt(self):
        self.agent_until = self.now()

    def stop(self):
        self.stopped.set()

    def save(self, path: Path) -> None:
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(SAMPLE_RATE)
            f.writeframes(self.timeline.tobytes())


def voice(args) -> None:
    el = client()
    print("Making the caller's lines with text to speech...")
    lines = [
        b"".join(
            el.text_to_speech.convert(
                voice_id=CALLER_VOICE,
                text=line,
                model_id="eleven_flash_v2_5",
                output_format="pcm_16000",
            )
        )
        for line in SCRIPT
    ]
    caller = SyntheticCaller(lines)

    def on_user(text: str) -> None:
        print(f"User (heard by the agent): {text}")

    def on_agent(text: str) -> None:
        print(f"Agent: {text}")
        caller.answered.set()

    conversation = Conversation(
        client=el,
        agent_id=agent_id(),
        user_id=CALLER_ID,
        requires_auth=True,
        audio_interface=caller,
        client_tools=client_tools(),
        callback_agent_response=on_agent,
        callback_user_transcript=on_user,
    )
    conversation.start_session()
    caller.done.wait(timeout=240)
    conversation.end_session()
    conversation_id = conversation.wait_for_session_end()
    STATE_DIR.mkdir(exist_ok=True)
    caller.save(STATE_DIR / "last-call.wav")
    print(f"Call audio: {STATE_DIR / 'last-call.wav'}")
    finish(conversation_id, args)


def finish(conversation_id: str, args) -> None:
    print(f"Conversation: {conversation_id}")
    if load_state().get("webhook_id") and not args.export:
        print("The post-call webhook forwards this trace once ElevenLabs has analyzed the call.")
        return
    export_conversation(conversation_id, args.save)


# --- forwarding ---------------------------------------------------------------


def fetch_otlp(el: ElevenLabs, conversation_id: str) -> dict:
    # ElevenLabs builds the trace after the call is analyzed. Until the
    # status is "done", the export can be missing turns.
    for _ in range(60):
        status = el.conversational_ai.conversations.get(conversation_id).status
        if status in ("done", "failed"):
            break
        time.sleep(5)
    conversation = el.conversational_ai.conversations.get(conversation_id, format="opentelemetry")
    return conversation.otlp_traces


def forward_to_oodle(otlp_traces: dict) -> None:
    response = requests.post(
        f"{oodle_endpoint()}/v1/traces",
        headers={
            "Content-Type": "application/json",
            "X-OODLE-INSTANCE": os.environ["OODLE_INSTANCE"],
            "X-API-KEY": os.environ["OODLE_API_KEY"],
        },
        data=json.dumps(otlp_traces),
        timeout=30,
    )
    response.raise_for_status()


def all_spans(otlp: dict) -> list[dict]:
    return [
        span
        for rs in otlp.get("resourceSpans", [])
        for ss in rs.get("scopeSpans", [])
        for span in ss.get("spans", [])
    ]


def export_conversation(conversation_id: str, save: str | None) -> None:
    otlp = fetch_otlp(client(), conversation_id)
    if save:
        Path(save).write_text(json.dumps(otlp, indent=2))
        print(f"Saved the trace to {save}")
    forward_to_oodle(otlp)
    spans = all_spans(otlp)
    trace_id = spans[0]["traceId"] if spans else "?"
    print(f"Forwarded {len(spans)} spans to Oodle. Trace id: {trace_id}")


def export(args) -> None:
    export_conversation(args.conversation_id, args.save)


def replay(args) -> None:
    """Forward a saved trace as a new one. ElevenLabs keeps one trace id per
    conversation, so a second copy under the same ids would merge into the
    first trace in Oodle."""
    otlp = json.loads(Path(args.file).read_text())
    spans = all_spans(otlp)
    trace_id = secrets.token_hex(16)
    new_ids = {s["spanId"]: secrets.token_hex(8) for s in spans}
    shift = time.time_ns() - max(int(s["endTimeUnixNano"]) for s in spans)
    conv_id = f"conv_replay_{random.randrange(16**8):08x}"
    for span in spans:
        span["traceId"] = trace_id
        span["spanId"] = new_ids[span["spanId"]]
        if span.get("parentSpanId"):
            span["parentSpanId"] = new_ids.get(span["parentSpanId"], span["parentSpanId"])
        span["startTimeUnixNano"] = str(int(span["startTimeUnixNano"]) + shift)
        span["endTimeUnixNano"] = str(int(span["endTimeUnixNano"]) + shift)
        for attr in span.get("attributes", []):
            if attr["key"] == "elevenlabs.conversation_id":
                attr["value"] = {"stringValue": conv_id}
    for rs in otlp.get("resourceSpans", []):
        for attr in rs.get("resource", {}).get("attributes", []):
            if attr["key"] == "elevenlabs.conversation_id":
                attr["value"] = {"stringValue": conv_id}
    forward_to_oodle(otlp)
    print(f"Forwarded {len(spans)} spans to Oodle. Trace id: {trace_id}, session: {conv_id}")


def teardown(_args) -> None:
    state = load_state()
    el = client()
    if state.get("agent_id"):
        el.conversational_ai.agents.delete(state["agent_id"])
    if state.get("document_id"):
        el.conversational_ai.knowledge_base.documents.delete(state["document_id"])
    if state.get("webhook_id"):
        el.webhooks.delete(state["webhook_id"])
    for f in (AGENT_FILE, SECRET_FILE):
        f.unlink(missing_ok=True)
    print("Deleted the demo agent, its knowledge base document and its webhook")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup").set_defaults(func=setup)
    p = sub.add_parser("webhook")
    p.add_argument("url", nargs="?", help="the forwarder's public base URL; omit to send straight to Oodle")
    p.set_defaults(func=webhook)
    for name, func in (("chat", chat), ("voice", voice)):
        p = sub.add_parser(name)
        p.add_argument("--export", action="store_true", help="fetch and forward the trace even with a webhook")
        p.add_argument("--save", help="also write the OTLP JSON to this file")
        p.set_defaults(func=func)
    p = sub.add_parser("export")
    p.add_argument("conversation_id")
    p.add_argument("--save", help="also write the OTLP JSON to this file")
    p.set_defaults(func=export)
    p = sub.add_parser("replay")
    p.add_argument("file")
    p.set_defaults(func=replay)
    sub.add_parser("teardown").set_defaults(func=teardown)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

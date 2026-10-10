"""A LiveKit voice agent that traces each call to Oodle, with or without PII.

The agent is a home-selling assistant: it checks valuation slots, books one
against the caller's name, phone number and address, and can hand the call
to a second agent that arranges a callback from a human. A conversation
like that is full of personal data, which is what makes the two PII modes
worth comparing:

- ``allow`` — Oodle receives the conversation: ``lk.pii.*`` transcripts,
  replies and tool arguments, and ``gen_ai.input/output.messages``.
- ``withhold`` — LiveKit strips all of that before export. Oodle receives
  the same span tree, timings, models, tokens and tool names, and no text.

The browser picks the mode per call; it arrives as dispatch metadata.

The shape mirrors a production LiveKit deployment: a ``voice_agent`` that
hands off to a ``transfer_agent``, an LLM behind a ``FallbackAdapter``, and
``agent.id`` / ``session.id`` / ``user.id`` / ``langfuse.*`` metadata on
every span. STT, LLM and TTS are all OpenAI so the demo needs one API key.

    python agent.py start
"""

import asyncio
import json
import logging
import os

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    llm,
)
from livekit.plugins import openai, silero

import tracing

logger = logging.getLogger("voice-agent")

# The OpenAI SDK reads OPENAI_BASE_URL itself and treats an empty value as
# a base URL of "", so every call would fail with "Connection error".
if not os.environ.get("OPENAI_BASE_URL", "").strip():
    os.environ.pop("OPENAI_BASE_URL", None)

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "livekit-voice-worker")
# The name the worker registers under; the browser's token dispatches to it.
AGENT_NAME = os.environ.get("AGENT_NAME", "livekit-demo-agent")
# The application's own id for this agent, stamped on every span.
AGENT_ID = os.environ.get("AGENT_ID", "maple-street-sales-agent")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "demo")

LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4.1-mini")
FALLBACK_LLM_MODEL = os.environ.get("FALLBACK_LLM_MODEL", "gpt-4o-mini")
STT_MODEL = os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "alloy")

SPOKEN = (
    "You are on a voice call, so your replies are spoken aloud: no emojis, lists "
    "or formatting, and keep each reply to a sentence or two."
)

VOICE_AGENT_INSTRUCTIONS = f"""\
You are Max, an assistant for Maple Street Realty, a fictional home-selling team.
Help the caller book a free home valuation. Ask which day suits them and use
check_availability to offer slots. To book, collect their full name, phone number
and the property address, read them back, then call book_valuation. If the caller
asks for a person, or for anything you cannot do, call transfer_to_agent.
{SPOKEN}"""

TRANSFER_AGENT_INSTRUCTIONS = f"""\
You arrange a callback from one of Maple Street Realty's human agents. Confirm the
best phone number to reach the caller on, call schedule_callback with it, tell them
an agent will ring within the hour, and say goodbye.
{SPOKEN}"""

# A stand-in calendar. Nothing in it identifies anyone.
OPEN_SLOTS = ["9:30 AM", "1:00 PM", "4:30 PM"]


class VoiceAgent(Agent):
    """Answers the call. Traced as ``lk.agent_label=voice_agent``."""

    def __init__(self) -> None:
        super().__init__(instructions=VOICE_AGENT_INSTRUCTIONS)

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions="Greet the caller as Max from Maple Street Realty and ask how you can help."
        )

    @function_tool
    async def check_availability(self, context: RunContext, day: str) -> str:
        """Look up the open home-valuation slots on a day.

        Args:
            day: The day the caller asked about, as they said it.
        """
        # Nothing personal goes in or comes out, but the arguments and the
        # result are still written under lk.pii.*: LiveKit cannot tell.
        return f"Open slots on {day}: {', '.join(OPEN_SLOTS)}."

    @function_tool
    async def book_valuation(
        self,
        context: RunContext,
        full_name: str,
        phone_number: str,
        address: str,
        day: str,
        slot: str,
    ) -> str:
        """Book a home valuation once the caller has confirmed their details.

        Args:
            full_name: The caller's full name.
            phone_number: The number to reach the caller on.
            address: The address of the property to value.
            day: The day of the valuation.
            slot: One of the open slots on that day.
        """
        logger.info("Booked a valuation on %s at %s", day, slot)
        return f"Booked {full_name} for {day} at {slot}, at {address}. A text goes to {phone_number}."

    @function_tool
    async def transfer_to_agent(self, context: RunContext) -> tuple[Agent, str]:
        """Hand the call to the team, when the caller asks for a person."""
        # Returning an agent hands the session to it. The trace records the
        # switch, and later spans carry lk.agent_label=transfer_agent.
        return TransferAgent(chat_ctx=self.chat_ctx), "Transferring you to the team."


class TransferAgent(Agent):
    """Takes over after a handoff. Traced as ``lk.agent_label=transfer_agent``."""

    def __init__(self, chat_ctx: llm.ChatContext) -> None:
        super().__init__(instructions=TRANSFER_AGENT_INSTRUCTIONS, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        self.session.generate_reply()

    @function_tool
    async def schedule_callback(self, context: RunContext, phone_number: str) -> str:
        """Ask a human agent to call the caller back.

        Args:
            phone_number: The number the caller wants to be called on.
        """
        return f"A callback to {phone_number} is queued for the next free agent."


def call_metadata(call: dict, job_id: str, mode: str) -> dict:
    """The attributes stamped on every span of one call.

    The same keys a production LiveKit agent tracing to Langfuse sets, so
    Oodle can group a call's spans by session and by contact. LiveKit
    stamps these on every span and never filters them, so they hold
    pseudonymous ids only: the contact id here, never a name or a number.
    """
    call_id = call.get("call_id") or job_id
    contact_id = call.get("contact_id") or "anonymous"

    return {
        "agent.id": AGENT_ID,
        "job.id": job_id,
        "session.id": call_id,
        "user.id": contact_id,
        "langfuse.session.id": call_id,
        "langfuse.user.id": contact_id,
        "langfuse.tags": [
            f"AI_AGENT_CALL_ID={call_id}",
            f"AI_AGENT_ID={AGENT_ID}",
            "AI_AGENT_CALL_TYPE=WEB",
            f"PII_MODE={mode}",
            f"ENV={ENVIRONMENT}",
            f"CONTACT_ID={contact_id}",
        ],
    }


def prewarm(proc: JobProcess) -> None:
    # Loaded once per job process, before a call is assigned to it.
    proc.userdata["vad"] = silero.VAD.load()


# One idle process is plenty for a demo; production's default is 14.
server = AgentServer(setup_fnc=prewarm, num_idle_processes=1)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    call = json.loads(ctx.job.metadata or "{}")
    mode = tracing.pii_mode(call.get("pii_mode"))

    # Before the session exists: spans recorded without a provider go nowhere.
    provider = tracing.init(
        SERVICE_NAME,
        metadata=call_metadata(call, ctx.job.id, mode),
        allow_pii=mode == tracing.PII_ALLOW,
    )

    async def flush_traces() -> None:
        # The agent_session span ends as the session closes, which is
        # before shutdown callbacks run.
        await asyncio.to_thread(provider.force_flush)

    ctx.add_shutdown_callback(flush_traces)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(model=STT_MODEL),
        # Two models behind a FallbackAdapter: if the first fails, the turn
        # retries on the second, and the trace shows an llm_fallback_adapter
        # span above the llm_request that answered.
        llm=llm.FallbackAdapter(
            [openai.LLM(model=LLM_MODEL), openai.LLM(model=FALLBACK_LLM_MODEL)]
        ),
        tts=openai.TTS(model=TTS_MODEL, voice=TTS_VOICE),
    )

    logger.info("Call %s started with pii_mode=%s", call.get("call_id"), mode)
    await session.start(agent=VoiceAgent(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)

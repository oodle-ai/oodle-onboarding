"""A Pipecat voice agent whose traces land in both Langfuse and Oodle.

A browser talks to the bot over WebRTC; speech goes through OpenAI
transcription, an OpenAI chat model and OpenAI speech synthesis. One API
key covers all three and the voice-activity detector runs locally, so the
demo needs no third-party voice vendor account.

The tracing is the point. Pipecat records a span tree per session:

    conversation                  conversation.id, conversation.type
    └── turn                      turn.number, turn.duration_seconds, …
        ├── stt                   transcript, language, metrics.ttfb
        ├── llm                   model, input/output, gen_ai.usage.*
        └── tts                   voice_id, text, metrics.character_count

``tracing.init()`` sends that tree to Langfuse and to Oodle at once, by
whichever of the two routes ``TRACING_BACKEND`` selects:

- ``otel`` — two OpenTelemetry OTLP exporters (``tracing_otel.py``)
- ``langfuse-sdk`` — the Langfuse Python SDK (``tracing_langfuse.py``)

Run it with the Pipecat development runner::

    python bot.py --host 0.0.0.0 --transport webrtc
"""

import logging
import os

import fastapi
from dotenv import load_dotenv
from loguru import logger
# FastAPI traces its own requests as soon as a tracer provider exists, and
# the Pipecat development runner is a FastAPI app: without this every
# static asset and signalling call becomes a trace of its own, and the
# session's `conversation` span is buried under the WebRTC offer request
# rather than being the root of its own trace. The runner builds its app
# at import time, so the default has to change before Pipecat is imported.
_fastapi_init = fastapi.FastAPI.__init__


def _no_http_telemetry(self, *args, **kwargs):
    kwargs.setdefault("telemetry", {"tracing": False, "operation_spans": False})
    _fastapi_init(self, *args, **kwargs)


fastapi.FastAPI.__init__ = _no_http_telemetry

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

import tracing

load_dotenv(override=True)

# The OpenAI SDK reads OPENAI_BASE_URL from the environment itself when it
# is constructed without a base_url, and it does not treat an empty value
# as absent: the base URL becomes "" and every call fails with
# "Connection error". A blank value is cleared here so that cannot happen,
# whichever layer set it.
if not os.environ.get("OPENAI_BASE_URL", "").strip():
    os.environ.pop("OPENAI_BASE_URL", None)

# The tracing modules log through the standard library while the rest of
# the demo logs through loguru. Without this their INFO lines are dropped,
# including the one that names both destinations, and OpenTelemetry's
# export failures arrive with no timestamp.
logging.basicConfig(
    level=logging.INFO,
    format="{asctime} | {levelname:<8} | {name} - {message}",
    style="{",
)

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "pipecat-demo")
AGENT_NAME = os.environ.get("AGENT_NAME", "pipecat-voice-agent")

LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
STT_MODEL = os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe")
TTS_MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "alloy")

SYSTEM_INSTRUCTION = (
    "You are a helpful assistant in a voice conversation. Your responses will be "
    "spoken aloud, so avoid emojis, bullet points, or other formatting that cannot "
    "be spoken. Keep answers to a sentence or two."
)

# Set up tracing before any pipeline exists: Pipecat's services read the
# tracer provider when the pipeline starts, and spans recorded before a
# provider is registered go nowhere.
TRACING_ENABLED = tracing.init(SERVICE_NAME)

# The runner picks a transport at connection time, so parameters are built
# lazily. Only WebRTC is wired up here; the demo needs no other.
transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Build and run one traced voice session."""
    api_key = os.environ["OPENAI_API_KEY"]
    base_url = os.environ.get("OPENAI_BASE_URL") or None

    stt = OpenAISTTService(
        api_key=api_key,
        base_url=base_url,
        settings=OpenAISTTService.Settings(model=STT_MODEL),
    )

    llm = OpenAILLMService(
        api_key=api_key,
        base_url=base_url,
        settings=OpenAILLMService.Settings(
            model=LLM_MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )

    tts = OpenAITTSService(
        api_key=api_key,
        base_url=base_url,
        settings=OpenAITTSService.Settings(model=TTS_MODEL, voice=TTS_VOICE),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        # Voice activity detection runs here, locally. It is what segments
        # the audio for transcription and what ends a turn, so it is also
        # what makes the `turn` spans line up with real turns.
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            # Without metrics the service spans carry no TTFB, and the LLM
            # span carries no token usage.
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        enable_tracing=TRACING_ENABLED,
        enable_turn_tracking=True,
        # These land on the conversation span. Oodle's agent-observability
        # views facet on the GenAI semantic conventions, and Pipecat writes
        # them on the service spans but has nothing to derive them from for
        # the span that wraps the session.
        additional_span_attributes={
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": AGENT_NAME,
        },
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected; starting the conversation")
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    try:
        await runner.run()
    finally:
        # The conversation span closes when the pipeline ends, so the flush
        # belongs after the runner rather than in the disconnect handler.
        # Flush, not shut down: the runner serves the next connection from
        # this same process, and a closed provider would drop its spans.
        if TRACING_ENABLED:
            logger.info("Flushing spans to Langfuse and Oodle")
            tracing.flush()


async def bot(runner_args: RunnerArguments):
    """Entry point the Pipecat runner calls for each connection."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()

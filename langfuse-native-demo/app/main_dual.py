"""The Langfuse SDK's own exporter, pointed at Langfuse and at Oodle.

The dual-write variant of `main.py`. The app keeps the Langfuse client it
already has — LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and
LANGFUSE_SECRET_KEY still address Langfuse — and Oodle is added as a
second destination for the same spans. There is still no OpenTelemetry
SDK pipeline in the app and no collector: both legs are the Langfuse
SDK's own exporter, writing to the Langfuse ingest API that Langfuse and
Oodle each serve.

Every observation the SDK writes is delivered twice, once to each
backend, and one flush covers both.
"""

import base64
import os

from langfuse import Langfuse, get_client, observe

# The Langfuse OpenAI drop-in traces every call it makes.
from langfuse.openai import openai
from opentelemetry import trace

# The span processor is the SDK's exporter. It is not re-exported at the
# package root, so it is imported from the module that defines it.
from langfuse._client.span_processor import LangfuseSpanProcessor

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


def required(name: str) -> str:
    """An unset variable is an error; an empty one disables tracing silently."""
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is required to write to both destinations")

    return value


# Both destinations are addressed by variables, so read them before the
# client is built rather than letting a blank key disable it quietly.
langfuse_public_key = required("LANGFUSE_PUBLIC_KEY")
required("LANGFUSE_SECRET_KEY")

# Destination one, unchanged: the client reads its three variables from
# the environment and registers its own processor and tracer provider.
langfuse = Langfuse()


def add_oodle_destination() -> None:
    """Add Oodle as a second destination for the SDK's spans."""
    instance = required("OODLE_INSTANCE")
    api_domain = os.environ.get("OODLE_API_DOMAIN", "us1.oodle.ai")

    # Oodle takes the Langfuse ingest credentials as the public key
    # `default` and the Oodle API key as the secret. The processor builds
    # its Authorization header from its own public_key and secret_key,
    # and merges additional_headers last — so these replace it.
    oodle_basic_auth = base64.b64encode(
        f"default:{required('OODLE_API_KEY')}".encode()
    ).decode()

    processor = LangfuseSpanProcessor(
        # A processor drops every Langfuse span whose instrumentation
        # scope carries a different public key, which is how the SDK
        # keeps two projects in one process apart. This leg carries the
        # spans of the client above, so it is that client's public key
        # here, not Oodle's.
        public_key=langfuse_public_key,
        secret_key="unused",
        base_url=f"https://{api_domain}/v1/api/instance/{instance}/langfuse",
        additional_headers={
            "Authorization": f"Basic {oodle_basic_auth}",
            "x-langfuse-public-key": "default",
        },
    )

    # The client registered its tracer provider as the global one. Adding
    # the processor there puts both legs behind every span the SDK writes.
    trace.get_tracer_provider().add_span_processor(processor)


add_oodle_destination()


# Group the LLM calls of one request under a single trace.
@observe()
def chat(message: str) -> str:
    response = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": message}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    print(chat("What is OpenTelemetry in one sentence?"))

    # One flush reaches both processors: it force-flushes the provider.
    get_client().flush()

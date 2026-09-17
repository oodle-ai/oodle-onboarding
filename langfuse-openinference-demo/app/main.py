"""A Langfuse `generation` observation around an OpenInference-instrumented
OpenAI call whose payload is redacted.

The model and the messages sit on the Langfuse span; the tokens sit on
the OpenInference child (`openinference.span.kind=LLM`), and only there.
Oodle reads both at ingest, so the trace prices, the transcript comes
from the Langfuse span, and the wrapper is not flagged as a generation
that returned no tokens.
"""

import os

from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# OpenInference hides the request and the response, as foothill does.
os.environ.setdefault("OPENINFERENCE_HIDE_INPUTS", "true")
os.environ.setdefault("OPENINFERENCE_HIDE_OUTPUTS", "true")

instance = os.environ["OODLE_INSTANCE"]
api_key = os.environ["OODLE_API_KEY"]

provider = TracerProvider(
    resource=Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "qa-planner"),
            "deployment.environment.name": "production",
        }
    )
)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=f"https://{instance}-otlp.collector.oodle.ai/v1/traces",
            headers={"X-API-KEY": api_key, "X-OODLE-INSTANCE": instance},
        )
    )
)
trace.set_tracer_provider(provider)
OpenAIInstrumentor().instrument(tracer_provider=provider)

# Langfuse attaches to the app's provider; its own exporter is not
# used, so nothing is delivered twice.
from langfuse import Langfuse, get_client, observe  # noqa: E402

Langfuse(
    public_key="default",
    secret_key=api_key,
    base_url=f"https://{os.environ.get('OODLE_API_DOMAIN', 'us1.oodle.ai')}"
    + f"/v1/api/instance/{instance}/langfuse",
    tracer_provider=provider,
    tracing_enabled=True,
)

from openai import OpenAI  # noqa: E402

client = OpenAI()
MODEL = os.environ.get("MODEL", "openai/gpt-4o-mini")

SYSTEM = "You are an expert senior software QA engineer. Reply with JSON."
USER = (
    "Maintain the customer-journey suite using this product change.\n"
    "<product_description>\n# Deployment commit batch\nNo changes.\n"
    "</product_description>\nReturn {\"additions\":[],\"revisions\":[]}."
)


@observe(as_type="generation", name="goal-qa-planner-attempt")
def attempt() -> str:
    lf = get_client()
    lf.update_current_generation(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        model_parameters={"reasoning_effort": "medium"},
        metadata={"attempt": 1, "pr_num": 0},
    )
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
    )
    text = resp.choices[0].message.content or ""
    lf.update_current_generation(output=text)
    return text


@observe(name="goal-qa-planner")
def planner() -> str:
    lf = get_client()
    lf.update_current_span(
        metadata={"existing_goal_count": 36, "max_new_goals": 464},
    )
    out = attempt()
    lf.update_current_span(output={"raw_response": out})
    return out


if __name__ == "__main__":
    print(planner()[:200])
    get_client().flush()
    provider.force_flush()
    provider.shutdown()

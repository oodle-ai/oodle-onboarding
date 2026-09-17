# Langfuse SDK + OpenInference demo

One Python service instrumented the way a Langfuse user often ends up:
the [Langfuse Python SDK](https://langfuse.com/docs/sdk/python) names
the observations (`@observe`, `@observe(as_type="generation")`), and
[OpenInference](https://github.com/Arize-ai/openinference) instruments
the OpenAI client underneath it, with the request and response hidden
(`OPENINFERENCE_HIDE_INPUTS` / `_OUTPUTS`). Both attach to the app's
OpenTelemetry tracer provider, which exports over OTLP to Oodle.

The trace that produces:

```
goal-qa-planner              Langfuse span     metadata
└── goal-qa-planner-attempt  Langfuse generation   model, the messages, the reply
    └── ChatCompletion       OpenInference LLM     tokens, `__REDACTED__` payload
```

The model and the transcript are on the Langfuse generation. The tokens
are on the OpenInference child, and only there. Oodle resolves both
namespaces at ingest, so:

- the trace prices from the child's tokens and the Langfuse span's model
- the Transcript reads the Langfuse generation, not the placeholder
- the wrapper is not reported as a generation that returned no tokens

## Quick start

```bash
cp .env.example .env
# Edit .env with your Oodle credentials and OpenAI key
make run
```

Then open Agent Observability > Traces and filter on service
`qa-planner`.

# Langfuse SDK native export demo

The [Langfuse Python SDK](https://langfuse.com/docs/sdk/python) with its
own exporter, pointed at Oodle. There is no OpenTelemetry SDK in the
app and no collector: Oodle serves the Langfuse ingest API, so the
client is configured with the three variables a Langfuse app already
has, and nothing in the code names Oodle.

```
LANGFUSE_BASE_URL=https://<API_DOMAIN>/v1/api/instance/<OODLE_INSTANCE>/langfuse
LANGFUSE_PUBLIC_KEY=default
LANGFUSE_SECRET_KEY=<OODLE_API_KEY>
```

This is the **Native SDK export** tab of the Langfuse tile. The
OpenTelemetry tab, where the SDK writes into a tracer provider the app
owns and every other span in the app arrives beside it, is
[`langfuse-demo`](../langfuse-demo). Only the spans the Langfuse SDK
writes are sent on this path.

The trace that produces:

```
chat                 Langfuse span         input, output
└── OpenAI-generation  Langfuse generation   model, messages, tokens
```

## Quick start

```bash
cp .env.example .env
# Edit .env with your Oodle credentials and OpenAI key
make run
```

Then open Agent Observability > Traces and filter on service
`langfuse-native-demo`.

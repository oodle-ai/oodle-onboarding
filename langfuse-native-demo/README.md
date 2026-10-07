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

## Dual-write to both Langfuse and Oodle

[`app/main_dual.py`](app/main_dual.py) keeps the Langfuse project the app
already reports to and adds Oodle as a second destination for the same
spans. Both legs are the Langfuse SDK's own exporter, so there is still
no OpenTelemetry SDK pipeline in the app and no collector.

```bash
# Set LANGFUSE_* to your Langfuse project and OODLE_* to your instance.
make run-dual
```

The three `LANGFUSE_*` variables keep their usual meaning — they address
Langfuse — and Oodle is configured beside them:

```
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

OODLE_INSTANCE=<OODLE_INSTANCE>
OODLE_API_KEY=<OODLE_API_KEY>
OODLE_API_DOMAIN=us1.oodle.ai
```

Each observation is delivered twice, and one `flush()` covers both:

```
                        ┌─► Langfuse     pk-lf-… / sk-lf-…
chat                    │   /api/public/otel/v1/traces
└── OpenAI-generation ──┤
                        └─► Oodle        default / <OODLE_API_KEY>
                            /v1/api/instance/<OODLE_INSTANCE>/langfuse/…
```

### Why it is written this way

Two `Langfuse()` clients do not work. A client's span processor drops
every Langfuse span whose instrumentation scope carries a different
public key — that is how the SDK keeps two projects in one process from
leaking into each other — and the decorator refuses to trace at all once
a second client exists:

```
No 'langfuse_public_key' passed to decorated function, but multiple langfuse
clients are instantiated in current process. Skipping tracing for this function
to avoid cross-project leakage.
```

So the variant keeps **one** client and adds a second
`LangfuseSpanProcessor` to the tracer provider that client registered.
Two details make that work:

- The processor is constructed with the **app's** Langfuse public key,
  not Oodle's, so the spans pass its project filter.
- Oodle's credentials — public key `default`, the Oodle API key as the
  secret — go in `additional_headers`, which the processor merges after
  the `Authorization` header it builds, replacing it.

`LangfuseSpanProcessor` is not re-exported at the package root, so it is
imported from `langfuse._client.span_processor`. The variant needs
Langfuse SDK v4 (v3's processor takes `host=` rather than `base_url=`).

# Oodle Onboarding: Official OTel GenAI Instrumentation

## What This Demonstrates

This setup shows how to use the [official OpenTelemetry GenAI instrumentation](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai/opentelemetry-instrumentation-google-genai) to auto-instrument Google Gemini calls and export telemetry to Oodle using only first-party OTel packages.

## How It Works

1. The **OpenTelemetry GenAI instrumentor** (`GoogleGenAiSdkInstrumentor`) auto-instruments Google Gemini API calls, capturing request/response details, token usage, latency, and model parameters as OpenTelemetry spans with `gen_ai.*` semantic conventions
2. **Prompt/response content** is captured as span attributes (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`) when using the experimental GenAI semantic conventions with `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_and_event`
3. Traces and logs are exported via OTLP HTTP to an **OpenTelemetry Collector**
4. The collector forwards telemetry to **Oodle** using the `-otlp` subdomain endpoint (`<instance>-otlp.collector.oodle.ai`) which supports standard OTLP paths

## Oodle Configuration

The OTel Collector is configured to export traces and logs to Oodle in `otel-collector-config.yaml`:

```yaml
exporters:
  otlphttp/oodle:
    endpoint: "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"
```

The `-otlp` subdomain supports standard OTLP paths (`/v1/traces`, `/v1/logs`, `/v1/metrics`), so no custom path configuration is needed.

## What You'll See in Oodle

After sending requests, navigate to **Traces** in your Oodle dashboard. You should see:

- **GenAI spans** following official OTel `gen_ai.*` semantic conventions
- **Token usage** (prompt tokens, completion tokens, total tokens)
- **Model information** (model name, parameters)
- **Prompt/response content** as span attributes (`gen_ai.input.messages`, `gen_ai.output.messages`)
- **Latency breakdown** across the full request lifecycle

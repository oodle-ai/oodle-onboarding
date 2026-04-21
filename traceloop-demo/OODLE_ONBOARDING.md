# Oodle Onboarding: Traceloop (OpenLLMetry)

## What This Demonstrates

This setup shows how to use [Traceloop's OpenLLMetry](https://github.com/traceloop/openllmetry) SDK to automatically instrument LLM calls (OpenAI) and export traces to Oodle.

## How It Works

1. The **Traceloop SDK** auto-instruments Google Gemini API calls, capturing request/response details, token usage, latency, and model parameters as OpenTelemetry spans
2. Traces are exported via OTLP HTTP to an **OpenTelemetry Collector**
3. The collector forwards traces to **Oodle** using the `-otlp` subdomain endpoint (`<instance>-otlp.collector.oodle.ai`) which supports standard OTLP paths

## Oodle Configuration

The OTel Collector is configured to export traces to Oodle in `otel-collector-config.yaml`:

```yaml
exporters:
  otlphttp/oodle:
    endpoint: "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"
```

The `-otlp` subdomain supports standard OTLP paths (`/v1/traces`, `/v1/metrics`), so no custom path configuration is needed.

## What You'll See in Oodle

After sending requests, navigate to **Traces** in your Oodle dashboard. You should see:

- **LLM call spans** with Gemini request/response details
- **Token usage** (prompt tokens, completion tokens, total tokens)
- **Model information** (model name, parameters)
- **Workflow spans** grouping related LLM calls (e.g., `chat`, `summarize`)
- **Latency breakdown** across the full request lifecycle

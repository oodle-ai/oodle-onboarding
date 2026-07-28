# Oodle Onboarding: OpenLit

## What This Demonstrates

This setup shows how to use the [OpenLit SDK](https://github.com/openlit/openlit) to automatically instrument AI applications and export telemetry to Oodle. It covers four OpenLit capabilities:

1. **AI Observability** — auto-instrument Google Gemini LLM calls, capturing token usage, cost, latency, and prompt/response content
2. **Guardrails** — screen user prompts for injection attacks, sensitive content, and topic violations before they reach the LLM
3. **VectorDB Observability** — auto-instrument ChromaDB operations in a RAG (Retrieval-Augmented Generation) pipeline
4. **MCP Observability** — auto-instrument Model Context Protocol tool calls between client and server

## How It Works

1. The **OpenLit SDK** is initialized with `openlit.init()` in the Flask app, the RAG server, and the MCP server. This single call auto-instruments all supported libraries (Google GenAI, ChromaDB, MCP) — no decorators or manual span creation needed
2. **Guardrails** use `openlit.guard.Pipeline` with `PromptInjection` and `SensitiveTopic` guards to check prompts via an LLM judge (Gemini through its OpenAI-compatible endpoint) before allowing them through to the main LLM call
3. **ChromaDB** operations (add documents, similarity search) run in the **RAG server** (`rag-server:8091`) and are automatically traced when `openlit.init()` is active
4. **MCP tool calls** from the client and tool executions on the server are automatically traced
5. Each service bridges Python `logging` to OTel via a `LoggerProvider` + `OTLPLogExporter`, so application logs are exported alongside traces
6. All telemetry is exported via OTLP HTTP to an **OpenTelemetry Collector**
7. The collector forwards traces, metrics, and logs to **Oodle** using the `-otlp` subdomain endpoint
8. A **redaction processor** strips PII (emails, credit card numbers, SSNs, phone numbers, API keys, JWTs) from all telemetry before export

## Oodle Configuration

The OTel Collector is configured to export traces, metrics, and logs to Oodle in `otel-collector-config.yaml`:

```yaml
exporters:
  otlphttp/oodle:
    endpoint: "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"

  otlphttp/oodle-logs:
    endpoint: "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"
```

The `-otlp` subdomain supports standard OTLP paths (`/v1/traces`, `/v1/metrics`, `/v1/logs`), so no custom path configuration is needed.

### PII Redaction

All pipelines use the `redaction` processor to scrub sensitive data before it leaves the collector. Matched values are replaced with `****`. The following patterns are blocked:

- Email addresses
- Credit/debit card numbers
- US Social Security Numbers
- Phone numbers
- API keys and bearer tokens
- JWT tokens

## What You'll See in Oodle

After sending requests, navigate to **Traces** in your Oodle dashboard. Filter by service name `openlit-demo`, `pokedex-rag`, or `openlit-mcp-server`.

### AI Observability traces (`/chat`, `/summarize`)
- **Gemini LLM spans** with model name, token usage (prompt/completion/total), and latency
- **Cost tracking** — estimated cost per LLM call
- **Prompt/response content** captured as span attributes

### Guardrail traces (`/safe-chat`)
- **Guard check spans** showing the prompt safety evaluation
- **Verdict, score, classification, and explanation** for each guard type (prompt injection, sensitive topics, topic restriction)
- **Blocked requests** visible as traces that end at the guard step without an LLM call

### VectorDB traces (`rag-server /query`, `/search`)
- **ChromaDB spans** for collection operations — `query`, `add`, `create_collection` (service: `pokedex-rag`)
- **Embedding and retrieval details** — query text, number of results, document IDs
- **End-to-end RAG trace** showing retrieval followed by LLM generation (on `/query`)

### MCP traces (`/mcp-search`)
- **MCP client spans** showing tool discovery and invocation
- **MCP server spans** (from `openlit-mcp-server` service) showing tool execution
- **Cross-service trace correlation** linking client and server spans

### Logs

All four services export application logs via OTLP. Navigate to **Logs** in Oodle and filter by service name. You'll see:

- **Request-level logs** — chat completions, summarizations, RAG queries, tool invocations
- **Guardrail denials** — `WARNING` logs when a prompt is blocked, including which guard triggered
- **Error logs** — LLM call failures, web search errors
- **Startup logs** — dataset loading (e.g. Pokemon data into ChromaDB)

Logs are correlated with traces via the W3C trace context, so clicking a log line links to its parent trace.

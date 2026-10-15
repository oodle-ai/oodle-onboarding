# Messages API (plain HTTP + API tracing)

Calls `POST /v1/messages` with `httpx` and no Claude SDK. The app emits
nothing about Claude itself. Every Claude span comes from Anthropic's side,
through the API tracing destination (see the [parent README](../README.md#api-tracing-destination)).
Without a destination this sub-demo produces only its own `demo.*` spans.

This shows that API tracing covers **any** client: curl, another language's
HTTP library, or a third-party tool.

## Joining Anthropic's spans to your trace

The app opens one span per scenario and injects that span's context into
the request headers:

```python
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

headers = {"x-api-key": ..., "anthropic-version": "2023-06-01", "content-type": "application/json"}
TraceContextTextMapPropagator().inject(headers)   # adds traceparent
httpx.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
```

Anthropic reads `traceparent` and makes its `anthropic.messages.create`
SERVER span a child of that span. If the header's sampled flag is off,
Anthropic emits no span for the request at all.

The same works from a shell:

```bash
TRACE_ID=$(openssl rand -hex 16); SPAN_ID=$(openssl rand -hex 8)
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -H "traceparent: 00-$TRACE_ID-$SPAN_ID-01" \
  -d '{"model": "claude-opus-5-5", "max_tokens": 256,
       "messages": [{"role": "user", "content": "Hello"}]}'
echo "search Oodle for trace $TRACE_ID"
```

## Scenarios

```bash
make messages-api                                         # all three
docker compose run --rm --build messages-api web_search   # one
```

| Scenario | Request | Spans from Anthropic |
|---|---|---|
| `chat` | One message | `anthropic.messages.create` > `anthropic.model_request` |
| `web_search` | `web_search_20260209` server tool | `anthropic.messages.create` > several `anthropic.model_request` + `anthropic.tool_use web_search` |
| `stream` | `"stream": true`, read over SSE | `anthropic.messages.create` > `anthropic.model_request` |

`web_search` is the interesting one. The search runs inside Anthropic, so
no client-side tracing could see it, but API tracing shows each model turn
and each search.

Requests send `"fallbacks": "default"` with the
`server-side-fallback-2026-07-01` beta header. If a safety classifier
declines a request, Anthropic re-runs it on its recommended fallback model.
Remove both to turn this off.

The app also copies the request id, response model, stop reason and token
counts onto its own span, so they're visible without a destination.

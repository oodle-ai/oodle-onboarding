# Pino Logs Demo

Ship [Pino](https://getpino.io) logs from a Node.js app to Oodle over
OpenTelemetry, with the trace id of the request on every line.

Two packages do the work:

- [`pino-opentelemetry-transport`](https://github.com/pinojs/pino-opentelemetry-transport)
  turns every log line into an OTLP log record and exports it. The
  level becomes the severity, the message the body, and the other
  fields attributes you can filter on.
- [`@opentelemetry/instrumentation-pino`](https://www.npmjs.com/package/@opentelemetry/instrumentation-pino)
  writes the active span's `trace_id` and `span_id` on each line, and
  the transport lifts them into the record's trace context. With the
  HTTP instrumentation opening a span per request, every line logged
  while a request is handled links to that request's trace.

## Architecture

```
POST /order | GET /crash
     |
     v
Node app (:8100) — pino + OTLP transport, HTTP + pino instrumentation
     |
     v
OTel Collector (OTLP :4318) --> Oodle (logs + traces)
```

## What Arrives

| Field in Oodle | Source |
|----------------|--------|
| `service` | `service.name` from the transport's `resourceAttributes` (or `OTEL_SERVICE_NAME`) |
| `message` | the Pino message |
| `norm_level` | the Pino level (`debug`, `info`, `warn`, `error`) |
| `log.attributes.*` | every other field on the line, such as `orderId`, `sku`, `err` |
| `trace_id`, `span_id` | the request span, from the Pino instrumentation |

## Two details that matter

- `app/logger.js` names the service on the transport. The transport
  runs in a worker thread and builds its own resource there; it does
  read `OTEL_SERVICE_NAME`, so either works, and the demo sets both
  so the logs and the traces agree.
- `app/instrumentation.js` passes `disableLogSending: true` to the
  Pino instrumentation. It can send records through the logs SDK as
  well, and with the transport already doing that, every line would
  arrive twice.

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)

## Quick Start

```bash
make help        # view available commands
```

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Send test requests:
   ```bash
   make test-order    # info and debug lines for one order
   make test-reject   # warn lines: unknown sku, quantity over limit
   make test-error    # an error line with a stack trace
   make test-all      # all of the above
   ```

## API Endpoints

### POST /order?sku=sku-200&qty=2
Places an order. Logs `order received`, `priced order` (debug) and
`order placed`, all with the order id, sku and quantity, through a
child logger. Rejects unknown skus and quantities over 10 with a warn
line, and fails a small share of orders at the payment step with an
error line.

### GET /crash
Logs an error with a stack trace and returns 500.

### GET /health
Health check.

## Viewing Logs in Oodle

1. Log in to your Oodle instance
2. Open the Logs Explorer (`/logs/app/data-explorer/discover`)
3. Filter on `service: pino-logs-demo`
4. Each line shows its level, message and fields. Click `trace_id`
   to open the request's trace, which lists the same lines.

## Cleanup

```bash
make clean
```

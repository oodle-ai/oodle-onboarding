# New Relic APM Demo

Two services instrumented with the **native New Relic APM agents** (not OTel),
talking to local Postgres, Redis and RabbitMQ. Mirrors a typical customer
setup so New Relic's APM, distributed tracing and database views can be
shown end to end.

```
curl ──> api (Node.js, newrelic npm agent) ──> Postgres
             │                              ──> Redis (cache-aside)
             └── RabbitMQ "orders" queue ──> worker (Python, newrelic pip agent) ──> Postgres
                                                                                 ──> Redis
```

| Service | Agent | What it does |
|---|---|---|
| `demo-api` | `newrelic` (Node) via `require('newrelic')` | Express: `/api/products` (Redis cache over Postgres), `POST /api/orders` (insert + publish), `/api/orders/:id`, `/api/stats` |
| `demo-worker` | `newrelic` (Python) via `newrelic-admin run-program` | Consumes `orders`, marks them processed in Postgres, bumps a Redis counter |

`api` runs **both** the New Relic agent and the OTel Node SDK in the same process
(`node -r newrelic -r @opentelemetry/auto-instrumentations-node/register`). The OTel side
reports as `demo-api-otel` through an OTel Collector to New Relic's OTLP endpoint, so the
same requests show up twice: as an APM entity and as an OpenTelemetry entity. Compare the
two pages to see which New Relic features need the native agent.

Both agents are configured purely through `NEW_RELIC_*` env vars in
`docker-compose.yml` — no `newrelic.js` / `newrelic.ini`. 5% of orders
reference a missing product so the API shows a non-zero error rate.

## Run

```bash
cp .env.example .env   # set NEW_RELIC_LICENSE_KEY (ingest license key)
make up                # includes a `load` container: bursts of traffic with random pauses
```

RabbitMQ management UI: http://localhost:15672 (guest/guest).

## What to look at in New Relic

- **APM & Services → demo-api / demo-worker**: throughput, latency, error rate (~5% on `POST /api/orders`).
- **Distributed tracing**: one trace spans `POST /api/orders` → RabbitMQ → the worker's `Message/RabbitMQ/Exchange/Named/Default` transaction.
- **Databases / External services**: Postgres and Redis call breakdown per transaction; `amqplib` / `pika` show up as message broker segments.
- Log forwarding is switched off in both agents and the OTel SDK (`NEW_RELIC_APPLICATION_LOGGING_FORWARDING_ENABLED=false`, `OTEL_LOGS_EXPORTER=none`) — this demo is APM only.

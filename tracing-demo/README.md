# Distributed Tracing Demo

This setup demonstrates end-to-end distributed tracing with OpenTelemetry across multi-language microservices (Go, Java, Python), with automatic load generation. All traces are collected by an OTel Collector and sent to Oodle.

See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for Oodle trace integration details.

## Architecture

```
load-generator (automatic, continuous)
       |
       v
frontend-api (Go :8080)
       |
       +---> java-service (:8081) -- "order-service"
       |        |
       |        +---> python-service (:8082) -- "inventory-service"
       |
       +---> go-service (:8083) -- "billing-service"
                |
                +---> python-service (:8082) -- "inventory-service"

All services --> OTel Collector (OTLP :4317/:4318) --> Oodle (traces)
```

## Components

| Service | Language | Port | Role | Instrumentation |
|---------|----------|------|------|-----------------|
| frontend-api | Go | 8080 | API Gateway | OTel SDK (otelhttp) |
| java-service | Java | 8081 | Order Service | OTel Java Agent (auto) |
| python-service | Python | 8082 | Inventory Service | OTel SDK + FlaskInstrumentor |
| go-service | Go | 8083 | Billing Service | OTel SDK (otelhttp) |
| load-generator | Python | - | Traffic Generator | N/A |
| otel-collector | - | 4317/4318 | Trace Collection | - |

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)

## Quick Start

View available options:
```bash
make help
```

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Oodle credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Traces start appearing automatically in Oodle — the load generator runs on startup and continuously sends requests every 3 seconds.

## Access Points

- **Frontend API**: http://localhost:8080
- **Java Service (Order)**: http://localhost:8081
- **Python Service (Inventory)**: http://localhost:8082
- **Go Service (Billing)**: http://localhost:8083

## Triggering Additional Traces

The load generator produces traces automatically. To send additional requests manually:

**Place an order** (triggers the full call chain):
```bash
curl -s -X POST http://localhost:8080/order \
  -H 'Content-Type: application/json' \
  -d '{"item":"widget","quantity":5}' | python3 -m json.tool
```

**Trace demo** (lightweight trace through frontend → java-service):
```bash
curl -s http://localhost:8080/trace-demo | python3 -m json.tool
```

**Health checks** (single-service spans):
```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8081/health
curl -s http://localhost:8082/health
curl -s http://localhost:8083/health
```

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to the **Traces** section
3. Filter by service name (e.g., `frontend-api`, `java-service`, `python-service`, `go-service`)
4. Click on a trace to view the full span waterfall across all services

You should see:
- **Service topology** showing how requests flow between services
- **Span details** with attributes like `order.item`, `order.quantity`, `inventory.in_stock`, `billing.total`
- **Cross-service trace propagation** with consistent trace IDs across Go, Java, and Python

## Service Details

### frontend-api (Go)
API gateway that receives incoming requests and fans out to downstream services.
- `POST /order` — Calls java-service and go-service in parallel, aggregates responses
- `GET /trace-demo` — Lightweight request that calls java-service health endpoint
- `GET /health` — Health check

### java-service (Java Spring Boot)
Order processing service instrumented automatically via the OTel Java Agent.
- `POST /process-order` — Processes an order and calls python-service to check inventory
- `GET /health` — Health check

### python-service (Python Flask)
Inventory and pricing service instrumented via OTel SDK with `FlaskInstrumentor` and custom spans.
- `GET /check-inventory?item=<item>` — Simulates inventory database lookup
- `GET /get-pricing?item=<item>` — Simulates pricing calculation
- `GET /health` — Health check

### go-service (Go)
Billing service instrumented via OTel SDK with `otelhttp`.
- `POST /calculate-billing` — Calculates billing and calls python-service for pricing
- `GET /health` — Health check

### load-generator (Python)
Automatic traffic generator that continuously sends requests to the frontend-api.
- Sends `POST /order` requests with random items and quantities
- Sends `GET /trace-demo` every 5th request for variety
- Configurable interval via `REQUEST_INTERVAL` environment variable (default: 3s)

## Troubleshooting

### Traces not appearing in Oodle

1. **Check OTel Collector logs for export errors:**
   ```bash
   make logs-collector
   ```

2. **Verify environment variables are set:**
   ```bash
   docker-compose config | grep OODLE
   ```

3. **Verify the Oodle endpoint is reachable:**
   ```bash
   curl -v "https://${OODLE_INSTANCE}.collector.oodle.ai/v1/otlp/traces"
   ```

### A service is not starting

1. **Check service logs:**
   ```bash
   make logs-frontend   # frontend-api
   make logs-java       # java-service
   make logs-python     # python-service
   make logs-go         # go-service
   make logs-loadgen    # load-generator
   ```

2. **Check service status:**
   ```bash
   make status
   ```

3. **Rebuild from scratch:**
   ```bash
   make clean
   make up
   ```

### Authentication errors

- Double-check your `OODLE_INSTANCE` and `OODLE_API_KEY` values in `.env`
- Ensure the API key has permissions for trace ingestion
- Generate a new API key from Oodle UI (Settings → API Keys) if needed

## Cleanup

Stop all services and remove volumes:
```bash
make clean
```

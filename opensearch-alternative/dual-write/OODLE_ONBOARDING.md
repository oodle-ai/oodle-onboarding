# Oodle Dual-Write Onboarding Guide

This guide documents the changes made to enable dual-write functionality, sending logs to both local OpenSearch and Oodle simultaneously.

## Overview

The dual-write setup allows you to:
- Continue using your local OpenSearch instance for development/testing
- Simultaneously send logs to Oodle for production observability
- Switch between agents (Fluent Bit, Vector, OpenTelemetry) seamlessly

## Architecture

```
                    ┌─────────────────┐
                    │   Demo App      │
                    │  (Go + OTel SDK)│
                    └────────┬────────┘
                             │
                    ┌────────▼─────────┐
                    │  Log Collection  │
                    │ Agent (Fluent Bit│
                    │ / Vector / OTel) │
                    └───┬──────────┬───┘
                        │          │
            ┌───────────▼──┐   ┌──▼─────────────┐
            │  OpenSearch  │   │     Oodle      │
            │   (Local)    │   │  (Production)  │
            └──────────────┘   └────────────────┘
```

## Prerequisites

1. **Oodle Instance and API Key**
   - Login to Oodle UI
   - Navigate to: Settings → API Keys
   - Note your `OODLE_INSTANCE` ID
   - Create or copy an existing `OODLE_API_KEY`

## Setup Instructions

### Step 1: Configure Environment Variables

1. Create a `.env` file in the `opensearch-alternative/dual-write` directory:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Oodle credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   ```

### Step 2: Start Services

Use the Makefile to start with your preferred agent:

```bash
# Start with Fluent Bit
make up AGENT=fluent-bit

# Or with Vector
make up AGENT=vector

# Or with OpenTelemetry
make up AGENT=otel
```

### Step 3: Verify Dual-Write

1. **Check local OpenSearch** (should have logs):
   ```bash
   curl http://localhost:9200/logs/_count
   ```

2. **Check Oodle UI**:
   - Login to your Oodle instance
   - Navigate to Logs section
   - You should see logs appearing with:
     - `service: demo-app`
     - Fields: `level`, `message`, `request_id`, `duration_ms`, `user_id`

## Configuration Changes

### 1. OpenTelemetry Collector (`agents/otel/otel-collector-config.yaml`)

**Added Oodle exporter:**
```yaml
exporters:
  # OpenSearch via Data Prepper (existing)
  otlp/opensearch:
    endpoint: data-prepper:21892
    tls:
      insecure: true

  # Oodle (NEW)
  otlphttp/oodle:
    logs_endpoint: "https://${OODLE_INSTANCE}-logs.collector.oodle.ai/ingest/otel/v1/logs"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"
```

**Updated pipeline to dual-write:**
```yaml
service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/opensearch, otlphttp/oodle]  # Both exporters
```

### 2. Vector (`agents/vector/vector.yaml`)

**Added Oodle sink:**
```yaml
sinks:
  # OpenSearch local (existing)
  opensearch:
    type: elasticsearch
    inputs: [add_timestamp]
    endpoints: ["http://opensearch:9200"]
    mode: bulk
    bulk:
      index: logs-%Y.%m.%d
    suppress_type_name: true

  # Oodle (NEW)
  oodle:
    type: http
    inputs: [add_timestamp]
    uri: "https://${OODLE_INSTANCE}-logs.collector.oodle.ai/ingest/v1/logs"
    encoding:
      codec: json
    compression: gzip
    request:
      headers:
        X-OODLE-INSTANCE: "${OODLE_INSTANCE}"
        X-API-KEY: "${OODLE_API_KEY}"
      retry_attempts: 3
      timeout_secs: 60
```

### 3. Fluent Bit (`agents/fluent-bit/fluent-bit.conf`)

**Added Oodle output:**
```conf
# OpenSearch local (existing)
[OUTPUT]
    Name                opensearch
    Match               *
    Host                opensearch
    Port                9200
    Index               logs
    Suppress_Type_Name  On
    tls                 Off

# Oodle (NEW)
[OUTPUT]
    Name                http
    Match               *
    Host                ${OODLE_INSTANCE}-logs.collector.oodle.ai
    Port                443
    URI                 /ingest/v1/logs
    Header              X-OODLE-INSTANCE ${OODLE_INSTANCE}
    Header              X-API-KEY ${OODLE_API_KEY}
    Format              json
    Compress            gzip
    Json_date_key       timestamp
    Json_date_format    iso8601
    TLS                 On
```

### 4. Docker Compose Files

**Added environment variables to each agent service:**

`docker-compose.otel.yml`:
```yaml
otel-collector:
  environment:
    - OODLE_INSTANCE=${OODLE_INSTANCE}
    - OODLE_API_KEY=${OODLE_API_KEY}
```

`docker-compose.vector.yml`:
```yaml
vector:
  environment:
    - OODLE_INSTANCE=${OODLE_INSTANCE}
    - OODLE_API_KEY=${OODLE_API_KEY}
```

`docker-compose.fluent-bit.yml`:
```yaml
fluent-bit:
  environment:
    - OODLE_INSTANCE=${OODLE_INSTANCE}
    - OODLE_API_KEY=${OODLE_API_KEY}
```

## Log Format

All agents send logs to Oodle in a consistent JSON format:

```json
{
  "timestamp": "2026-02-12T12:30:45Z",
  "level": "INFO",
  "message": "Processing user request",
  "service": "demo-app",
  "log": {
    "request_id": "abc123xyz",
    "duration_ms": 245,
    "user_id": 42
  }
}
```

For OTel specifically, additional OpenTelemetry metadata is included:
- `resource.attributes.*`: SDK metadata
- `instrumentationScope.name`: Logger name
- `severityText`, `severityNumber`: Log levels

## Troubleshooting

### Logs not appearing in Oodle

1. **Verify environment variables are set:**
   ```bash
   docker-compose -f docker-compose.base.yml -f docker-compose.otel.yml config | grep OODLE
   ```

2. **Check agent logs for errors:**
   ```bash
   # For OTel
   docker-compose -f docker-compose.base.yml -f docker-compose.otel.yml logs otel-collector

   # For Vector
   docker-compose -f docker-compose.base.yml -f docker-compose.vector.yml logs vector

   # For Fluent Bit
   docker-compose -f docker-compose.base.yml -f docker-compose.fluent-bit.yml logs fluent-bit
   ```

3. **Verify Oodle endpoint is reachable:**
   ```bash
   curl -v https://${OODLE_INSTANCE}-logs.collector.oodle.ai/health
   ```

### Authentication errors

- Double-check your `OODLE_INSTANCE` and `OODLE_API_KEY` values
- Ensure the API key has permissions for log ingestion
- Generate a new API key from Oodle UI if needed

### No logs in local OpenSearch

- This is independent of Oodle integration
- Check OpenSearch is running: `curl http://localhost:9200`
- Verify the specific agent's local output configuration

## Benefits of Dual-Write

1. **Zero Downtime Migration**: Test Oodle integration while keeping existing setup
2. **Data Validation**: Compare logs between local and cloud to ensure consistency
3. **Gradual Rollout**: Validate Oodle integration before fully migrating
4. **Development Flexibility**: Use local OpenSearch for dev, Oodle for production

## Production Considerations

### Option 1: Keep Dual-Write (Recommended for hybrid setups)
- Development environments → Local OpenSearch
- Production environments → Oodle
- Both destinations receive logs for redundancy

### Option 2: Migrate Fully to Oodle
Once validated, remove local OpenSearch outputs:

**OTel:** Remove `otlp/opensearch` from exporters list
**Vector:** Remove `opensearch` sink
**Fluent Bit:** Remove `opensearch` OUTPUT section

### Cost Optimization

Monitor log volume to optimize costs:
- Use sampling for high-volume applications
- Filter out debug logs in production
- Implement log level-based routing

## Support

- **Oodle Support**: support@oodle.ai
- **Documentation**: Check Oodle UI → Settings → Integrations for latest configs
- **Issues**: Report issues in this repository

## References

- [Oodle OpenTelemetry Integration](https://docs.oodle.ai/integrations/logs/otel)
- [Oodle Vector Integration](https://docs.oodle.ai/integrations/logs/vector)
- [Oodle Fluent Bit Integration](https://docs.oodle.ai/integrations/logs/fluentbit)

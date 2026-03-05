# Oodle Dual-Write Onboarding Guide

This guide documents the changes made to enable dual-write functionality, sending metrics to both Datadog and Oodle simultaneously using the Datadog Agent's native dual-shipping feature.

## Overview

The dual-write setup allows you to:
- Continue using your existing Datadog setup for monitoring
- Simultaneously send metrics to Oodle for evaluation
- Choose between environment variable or YAML configuration methods
- Validate metrics arrive correctly in Oodle before cutting over

See [README.md](./README.md) for architecture diagrams, metrics details, and quick-start commands.

## Prerequisites

1. **Datadog Account and API Key**
   - An existing Datadog account
   - A valid `DD_API_KEY` from your Datadog organization

2. **Oodle Instance and API Key**
   - Login to Oodle UI
   - Navigate to: Settings -> Integrations -> Datadog
   - Note your Oodle endpoint URL
   - Choose or create an Oodle API key

## Setup Instructions

### Step 1: Configure Environment Variables

1. Create a `.env` file in the `datadog-alternative/dual-write` directory:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   # Datadog
   DD_API_KEY=your-datadog-api-key
   DD_SITE=datadoghq.com

   # Oodle (for dual-write)
   OODLE_ENDPOINT=https://your-oodle-endpoint
   OODLE_API_KEY=your-oodle-api-key
   ```

### Step 2: Choose a Configuration Method

#### Option A: Environment Variable Method

Start with the env var method (no additional file edits needed):

```bash
make up METHOD=env
```

This sets `DD_ADDITIONAL_ENDPOINTS` on the Datadog Agent container, which tells the agent to send metrics to Oodle in addition to Datadog.

#### Option B: YAML Config Method

1. Edit `config/datadog.yaml` with your Oodle credentials:
   ```yaml
   additional_endpoints:
     "https://your-oodle-endpoint":
       - your-oodle-api-key
   ```

   Note: For this method, the Oodle credentials are configured directly in the YAML file rather than through `.env` variables.

2. Start with the YAML config method:
   ```bash
   make up METHOD=yaml-config
   ```

### Step 3: Verify Dual-Write

1. **Check demo app is emitting metrics:**
   ```bash
   make logs-app
   ```
   You should see output like:
   ```
   Sent metrics: GET /api/users -> 200 (123.4ms)
   ```

2. **Check Datadog Agent is running:**
   ```bash
   make logs-agent
   ```

3. **Check Datadog UI:**
   - Login to your Datadog account
   - Navigate to Metrics -> Explorer
   - Search for metrics with the `demo.` prefix

4. **Check Oodle UI:**
   - Login to your Oodle instance
   - Navigate to the Metrics section
   - You should see metrics appearing with:
     - Namespace: `demo.`
     - Tags: `service:demo-app`, `env:dev`

## Configuration Changes

### Method 1: Environment Variable (`docker-compose.env.yml`)

**Added `DD_ADDITIONAL_ENDPOINTS` to the Datadog Agent:**
```yaml
services:
  datadog-agent:
    environment:
      DD_ADDITIONAL_ENDPOINTS: '{"${OODLE_ENDPOINT}": ["${OODLE_API_KEY}"]}'
```

This uses the Datadog Agent's native `DD_ADDITIONAL_ENDPOINTS` environment variable. The agent parses this JSON and sends all metric payloads to the specified additional endpoints alongside the primary Datadog endpoint.

### Method 2: YAML Config File (`docker-compose.yaml-config.yml`)

**Mounted a custom `datadog.yaml` into the agent container:**
```yaml
services:
  datadog-agent:
    volumes:
      - ./config/datadog.yaml:/etc/datadog-agent/datadog.yaml:ro
```

**The `config/datadog.yaml` adds `additional_endpoints`:**
```yaml
additional_endpoints:
  "https://your-oodle-endpoint":
    - your-oodle-api-key

dogstatsd_non_local_traffic: true
```

This achieves the same result as the environment variable method but through the agent's configuration file, which is the standard approach for on-premise or VM-based deployments.

### Docker Compose Base (`docker-compose.base.yml`)

**Core services defined:**
```yaml
services:
  datadog-agent:
    image: gcr.io/datadoghq/agent:7
    environment:
      - DD_API_KEY=${DD_API_KEY}
      - DD_SITE=${DD_SITE:-datadoghq.com}
      - DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true
    ports:
      - "8125:8125/udp"   # DogStatsD
      - "8126:8126"       # APM

  demo-app:
    build: ./app
    environment:
      - DOGSTATSD_ADDR=datadog-agent:8125
```

## Troubleshooting

### Metrics not appearing in Oodle

1. **Verify environment variables are set (env method):**
   ```bash
   docker-compose -f docker-compose.base.yml -f docker-compose.env.yml config | grep -A2 DD_ADDITIONAL
   ```

2. **Check Datadog Agent logs for errors:**
   ```bash
   make logs-agent
   ```

3. **Verify the Oodle endpoint is correct:**
   - Login to Oodle UI -> Settings -> Integrations -> Datadog
   - Confirm the endpoint URL matches your configuration

### Datadog Agent not starting

- Ensure `DD_API_KEY` is set in your `.env` file
- A valid Datadog API key is required even for dual-write setups

### Demo app connection errors

- Ensure the Datadog Agent is running and healthy
- Check that `DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true` is set (allows non-localhost connections)
- Verify the `DOGSTATSD_ADDR` environment variable points to `datadog-agent:8125`

### Authentication errors with Oodle

- Double-check your Oodle endpoint URL and API key
- Ensure the API key has permissions for metric ingestion
- Generate a new API key from the Oodle UI if needed

## Benefits of Dual-Write for Migration

- **Zero downtime**: Continue using Datadog while evaluating Oodle
- **Data validation**: Compare metrics in both platforms side by side
- **Gradual migration**: Cut over to Oodle when ready by removing the Datadog primary endpoint

## Support

- Email: support@oodle.ai
- Docs: https://docs.oodle.ai
- Issues: https://github.com/oodle-ai/oodle-onboarding/issues

## References

- [Oodle Datadog Integration](https://docs.oodle.ai/integrations/metrics/datadog/)
- [Datadog Dual Shipping Guide](https://docs.datadoghq.com/agent/guide/dual-shipping/)
- [Datadog Agent Configuration](https://docs.datadoghq.com/agent/configuration/agent-configuration-files/)

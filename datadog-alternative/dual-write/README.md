# Migrating from Datadog

This setup demonstrates how to dual-write metrics from a Datadog Agent to both Datadog and Oodle. It spins up a Datadog Agent with a demo application emitting metrics via DogStatsD, so you can see how an existing Datadog pipeline can be extended to send metrics to Oodle with minimal configuration changes.

See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for dual-write setup instructions.

## Components

- **demo-app**: Go application that emits metrics via DogStatsD (counters, gauges, histograms, distributions)
- **datadog-agent**: Datadog Agent that receives DogStatsD metrics and forwards them
- **Configuration method** (choose one):
  - **env**: Dual-write configured via `DD_ADDITIONAL_ENDPOINTS` environment variable
  - **yaml-config**: Dual-write configured via `datadog.yaml` configuration file

## Quick Start

View available options:
```bash
make help
```

Start with environment variable method (default):
```bash
make up
# or explicitly
make up METHOD=env
```

Start with YAML config method:
```bash
make up METHOD=yaml-config
```

View logs:
```bash
make logs           # All services
make logs-app       # Application only
make logs-agent     # Datadog Agent only
```

Stop services:
```bash
make down           # Stop all
make clean          # Stop and remove volumes
```

## Configuration Methods

Both methods achieve the same result -- dual-writing metrics to Datadog and Oodle. Pick the one that matches your existing setup.

### Environment Variable Method (`env`)
- **Approach**: Sets `DD_ADDITIONAL_ENDPOINTS` on the Datadog Agent container
- **Config**: Environment variable in `docker-compose.env.yml`
- **Best for**: Quick setup, containerized deployments, Kubernetes

### YAML Config Method (`yaml-config`)
- **Approach**: Mounts a `datadog.yaml` with `additional_endpoints` configured
- **Config**: `config/datadog.yaml`
- **Best for**: Existing deployments with managed config files, on-premise setups

## Metrics Emitted

The demo app emits the following metrics with the `demo.` namespace:

| Metric | Type | Description |
|--------|------|-------------|
| `demo.http.requests.total` | Counter | Total HTTP requests |
| `demo.http.request.duration_ms` | Histogram | Request duration in milliseconds |
| `demo.http.active_connections` | Gauge | Current active connections |
| `demo.system.cpu_usage_percent` | Gauge | Simulated CPU usage |
| `demo.system.memory_usage_mb` | Gauge | Simulated memory usage |
| `demo.http.request.payload_bytes` | Distribution | Request payload sizes |

Tags applied: `service:demo-app`, `env:dev`, `endpoint:*`, `method:*`, `status_code:*`

## Architecture

### Dual-Write Flow
```
demo-app --DogStatsD (UDP)--> Datadog Agent --HTTPS--> Datadog  (primary)
                                            --HTTPS--> Oodle    (additional endpoint)
```

The Datadog Agent's native [dual-shipping](https://docs.datadoghq.com/agent/guide/dual-shipping/) feature sends the same metric payloads to both endpoints simultaneously.

## Switching Methods

To switch between configuration methods:

```bash
# Stop current setup
make down

# Start with different method
make up METHOD=yaml-config
```

Or use restart:
```bash
make restart METHOD=env
```

## References

- [Oodle Datadog Integration](https://docs.oodle.ai/integrations/metrics/datadog/)
- [Datadog Dual Shipping Guide](https://docs.datadoghq.com/agent/guide/dual-shipping/)

# Datadog Agent Configuration

This directory contains the Datadog Agent configuration file used by the YAML config method.

## `datadog.yaml`

Configures the Datadog Agent to dual-write metrics to both Datadog and Oodle using the `additional_endpoints` directive.

### Setup

Before using, edit `datadog.yaml` and replace the placeholder values:

1. Replace `https://your-oodle-endpoint` with your Oodle endpoint URL
2. Replace `your-oodle-api-key` with your Oodle API key

Both values are available in the Oodle UI under Settings -> Integrations -> Datadog.

> **Note**: The environment variable method (`docker-compose.env.yml`) does not require editing this file. It configures dual-write entirely through the `DD_ADDITIONAL_ENDPOINTS` environment variable. Use whichever method matches your deployment style.

## How It Works

The Datadog Agent natively supports sending metrics to multiple endpoints via the [`additional_endpoints`](https://docs.datadoghq.com/agent/guide/dual-shipping/) configuration. Oodle exposes a Datadog-compatible intake endpoint, so the agent treats it as another Datadog backend.

```
Demo App --DogStatsD--> Datadog Agent --HTTPS--> Datadog (primary)
                                      --HTTPS--> Oodle   (additional endpoint)
```

## References

- [Oodle Datadog Integration](https://docs.oodle.ai/integrations/metrics/datadog/)
- [Datadog Dual Shipping Guide](https://docs.datadoghq.com/agent/guide/dual-shipping/)
- [Datadog Agent Config Template](https://github.com/DataDog/datadog-agent/blob/main/pkg/config/config_template.yaml)

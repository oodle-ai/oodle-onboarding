# Datadog Agent Configuration

This directory contains the Datadog Agent configuration file used by the YAML config method (`make up METHOD=yaml-config`).

## Setup

Edit `datadog.yaml` and replace the placeholder values with your Oodle credentials (available in the Oodle UI under Settings -> Integrations -> Datadog).

> **Note**: The environment variable method (`make up METHOD=env`) does not require editing this file.

## References

- [Oodle Datadog Integration](https://docs.oodle.ai/integrations/metrics/datadog/)
- [Datadog Dual Shipping Guide](https://docs.datadoghq.com/agent/guide/dual-shipping/)

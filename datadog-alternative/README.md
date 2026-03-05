# Migrating from Datadog

Demonstrates how to migrate from Datadog to Oodle using the Datadog Agent's native dual-shipping feature.

## Available Setups

### [dual-write](./dual-write)

Datadog Agent setup that mirrors a typical production deployment, ready for dual-write to Oodle:
- Go application emitting metrics via DogStatsD
- Datadog Agent with dual-shipping to both Datadog and Oodle
- Two configuration methods (environment variable or YAML config file)
- Oodle dual-write to validate migration

**Use case**: Run the Datadog Agent locally, enable dual-write to Oodle, and verify metrics arrive correctly before cutting over.

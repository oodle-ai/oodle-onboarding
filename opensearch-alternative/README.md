# Migrating from OpenSearch

Demonstrates how to migrate from OpenSearch to Oodle using different log collection agents.

## Available Setups

### [dual-write](./dual-write)

Local OpenSearch stack that mirrors a typical production setup, with dual-write to Oodle:
- Go application emitting structured logs
- Multiple log collection agents (Fluent Bit, Vector, OTel Collector)
- Local OpenSearch + Dashboards for comparison
- Oodle dual-write to validate migration

**Use case**: Run OpenSearch locally, enable dual-write to Oodle, and verify logs arrive correctly before cutting over.

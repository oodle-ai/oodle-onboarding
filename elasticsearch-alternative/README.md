# Migrating from Elasticsearch

Demonstrates how to migrate from Elasticsearch to Oodle using different log collection agents.

## Available Setups

### [dual-write](./dual-write)

Local Elasticsearch stack that mirrors a typical production setup, ready for dual-write to Oodle:
- Go application emitting structured logs
- Multiple log collection agents (Fluent Bit, Vector, OTel Collector)
- Local Elasticsearch + Kibana for comparison
- Oodle dual-write support (coming soon)

**Use case**: Run Elasticsearch locally, enable dual-write to Oodle, and verify logs arrive correctly before cutting over.

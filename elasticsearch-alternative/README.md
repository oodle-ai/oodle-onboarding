# Elasticsearch Alternative

Demonstrations of integrating applications with Elasticsearch for log aggregation, search, and analytics.

## Available Setups

### [dual-write](./dual-write)

Complete logging stack with:
- Go application emitting structured logs
- Multiple log collection agents (Fluent Bit, Vector, OTel Collector)
- Elasticsearch cluster
- Kibana for visualization

**Use case**: Local development environment for testing log ingestion and search.

## What is Elasticsearch?

Elasticsearch is a distributed search and analytics engine. It provides:
- Full-text search
- Log analytics
- Real-time application monitoring
- APM and observability

## When to Use This Alternative

- Need a mature search and analytics engine
- Require log aggregation and analysis
- Want Kibana for visualization and dashboards
- Need the Elastic ecosystem (Beats, Logstash, APM)

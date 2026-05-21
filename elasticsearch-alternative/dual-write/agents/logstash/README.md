# Logstash Agent

Classic ELK stack log processing pipeline.

## Configuration

**pipeline.conf** contains:
- **Input**: GELF input on port 12201 (receives from Docker GELF logging driver)
- **Filter**: JSON parsing, field promotion, and timestamp extraction
- **Output**: Dual-write to Elasticsearch and Oodle

## How It Works

1. Demo app logs structured JSON to stdout
2. Docker GELF logging driver forwards log entries to Logstash (port 12201)
3. Logstash parses the JSON message, extracts fields, and sets `@timestamp`
4. Sends to both Elasticsearch (local) and Oodle (dual-write)

## Why Logstash?

- **Classic ELK stack**: The most common pipeline in existing Elasticsearch deployments
- **Rich filter ecosystem**: Grok, mutate, date, and hundreds of other filters
- **Familiar to Elasticsearch users**: If you already run ELK, this is the natural migration path
- **Powerful transformations**: Complex parsing and enrichment before indexing

## Resource Usage

- Memory: ~300-500 MB (JVM-based)
- CPU: Moderate
- Best for: Existing ELK stack deployments migrating to Oodle

# Fluent Bit Agent

Lightweight log processor and forwarder.

## Configuration

- **fluent-bit.conf**: Main configuration
  - Input: Forward protocol (receives from Docker fluentd driver)
  - Filter: JSON parser for log messages
  - Output: OpenSearch with index name `logs`

- **parsers.conf**: JSON parser definition

## How It Works

1. Demo app logs to stdout
2. Docker fluentd logging driver forwards to Fluent Bit (port 24224)
3. Fluent Bit parses JSON logs
4. Sends to OpenSearch

## Resource Usage

- Memory: ~20-40 MB
- CPU: Minimal
- Best for: High-volume log forwarding with low overhead

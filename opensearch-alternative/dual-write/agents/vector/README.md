# Vector Agent

High-performance observability data pipeline.

## Configuration

**vector.toml** contains:
- **Source**: Reads logs from Docker containers via socket
- **Transform**: Parses JSON from log messages
- **Sink**: Sends to OpenSearch with daily indices

## How It Works

1. Demo app logs to stdout
2. Vector reads directly from Docker logs (via `/var/run/docker.sock`)
3. Parses and transforms JSON
4. Bulk writes to OpenSearch with date-based indices

## Features

- No Docker logging driver required
- Built-in VRL (Vector Remap Language) for transformations
- High throughput with batching
- Observability of the pipeline itself

## Resource Usage

- Memory: ~50-100 MB
- CPU: Low to moderate
- Best for: Complex transformations and high-throughput scenarios

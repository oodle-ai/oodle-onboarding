# oodle-onboarding

Working examples showing how to integrate with the [Oodle](https://oodle.ai) observability platform for logs, metrics, and traces.

## Available Integrations

| Integration | Signal | Description |
|------------|--------|-------------|
| [elasticsearch-alternative/dual-write](./elasticsearch-alternative/dual-write) | Logs | Migrate from Elasticsearch — dual-write to ES + Oodle via Fluent Bit, Vector, OTel Collector, or Filebeat+Logstash |
| [elasticsearch-alternative/single-write](./elasticsearch-alternative/single-write) | Logs | Baseline Elasticsearch-only setup (no Oodle) |
| [opensearch-alternative/dual-write](./opensearch-alternative/dual-write) | Logs | Migrate from OpenSearch — dual-write to OS + Oodle via Fluent Bit, Vector, or OTel Collector |
| [datadog/dual-write](./datadog/dual-write) | Metrics, traces, logs | Dual-ship from Datadog Agent to both Datadog and Oodle using native `DD_ADDITIONAL_ENDPOINTS` |
| [datadog/single-write](./datadog/single-write) | Metrics, traces, logs | Baseline Datadog-only setup (no Oodle) |
| [datadog/oodle-single-write](./datadog/oodle-single-write) | Metrics, traces, logs | Send from Datadog Agent to Oodle only — redirect primary endpoints, no data to Datadog |
| [datadog/otel-dual-write](./datadog/otel-dual-write) | Traces, metrics, logs | Dual-write from OTel Collector to both Datadog and Oodle — mirrors a Cloud Run sidecar pattern |
| [datadog/ecs](./datadog/ecs) | Metrics, traces, logs | Terraform demos running a single Datadog-instrumented ECS task — Fargate and EC2 flavors — via the `terraform-aws-ecs-datadog` module, plus the account-level AWS integration |
| [tracing-demo](./tracing-demo) | Traces | End-to-end distributed tracing across Go, Java, and Python microservices with OpenTelemetry |
| [traceloop-demo](./traceloop-demo) | Traces | LLM observability using Traceloop's OpenLLMetry SDK with Google Gemini |
| [llmops-otel-demo](./llmops-otel-demo) | Traces | LLM observability using official OpenTelemetry GenAI instrumentation with Google Gemini |
| [pydantic-ai-demo](./pydantic-ai-demo) | Traces | AI agent observability using Pydantic AI with built-in OTel GenAI instrumentation |
| [k8s-otel-operator](./k8s-otel-operator) | Traces, metrics, logs | Zero-code auto-instrumentation on Kubernetes via the OpenTelemetry Operator |
| [temporal-demo](./temporal-demo) | Metrics, traces, logs | Temporal workflow observability with self-hosted server, Python SDK, and OTel |
| [convox-demo](./convox-demo) | Logs | Deploy a Rails app on Convox v2 (AWS ECS) and route each app's logs to Oodle via a host-local Fluent Bit agent (per-app identity resolved from ECS introspection); dual-write to CloudWatch during migration, then single-write to Oodle — no app code changes |

## Getting Started

Every example follows the same pattern:

```bash
cd <integration-directory>
cp .env.example .env
# Edit .env with your Oodle credentials (and any vendor-specific keys)
make up
```

Each setup is self-contained — no shared dependencies between integrations.

## For AI Agents

See [`llms.txt`](./llms.txt) for a machine-readable index of all examples with metadata (languages, signals, config file paths, agent options, and Oodle endpoint reference).

## Development

### Prerequisites

- Go 1.25+
- Docker & Docker Compose
- [pre-commit](https://pre-commit.com/#install) (for git hooks)
- [golangci-lint](https://golangci-lint.run/usage/install/) (for Go linting)

### Setup

Install pre-commit hooks:
```bash
make setup-hooks
```

### Linting and Formatting

```bash
make lint    # Run all linters
make fmt     # Format all Go code
make check   # Run all pre-commit checks
```

## Adding New Integrations

1. Create a top-level folder named after the vendor/tool
2. Organize by setup type (e.g., `single-write/`, `dual-write/`, or by language)
3. Include a README explaining what the integration demonstrates
4. Include a `.env.example` with required variables
5. Include a `Makefile` with `up`, `down`, `clean`, `logs`, and `help` targets
6. Keep each setup completely self-contained
7. Update this README table and `llms.txt` with the new integration

# OTel Operator Auto-Instrumentation Demo

Demonstrates zero-code distributed tracing on Kubernetes using the [OpenTelemetry Operator](https://opentelemetry.io/docs/platforms/kubernetes/operator/) for automatic instrumentation. All telemetry is collected by an operator-managed OTel Collector and exported to Oodle.

**Key difference from `tracing-demo`**: the application code contains **no OTel SDK imports or instrumentation code**. The OTel Operator injects instrumentation automatically via pod annotations.

## Architecture

```
load-generator (continuous)
       |
       v
frontend (Node.js :3000)
       |
       +---> order-service (Python :5000)
       |
       +---> payment-service (Java :8080)

                    ┌──────────────────────────────────┐
All services ──────>│ OTel Collector (Operator-managed) │────> Oodle
 (auto-injected)    │ OTLP :4317 (gRPC) / :4318 (HTTP) │
                    └──────────────────────────────────┘
```

## Components

| Service | Language | Port | Auto-Instrumentation | Annotation |
|---------|----------|------|---------------------|------------|
| frontend | Node.js | 3000 | OTel JS SDK (injected) | `inject-nodejs: "true"` |
| order-service | Python | 5000 | OTel Python SDK (injected) | `inject-python: "true"` |
| payment-service | Java | 8080 | OTel Java Agent (injected) | `inject-java: "true"` |
| load-generator | Python | - | None (traffic only) | - |

## How It Works

1. **OTel Operator** watches for pods with `instrumentation.opentelemetry.io/inject-<lang>` annotations
2. When a matching pod starts, the operator adds an init container that injects the OTel SDK/agent
3. The injected SDK sends telemetry to the **OTel Collector** (deployed via `OpenTelemetryCollector` CRD)
4. The collector exports traces, metrics, and logs to **Oodle** via OTLP/HTTP

No application code changes required.

## Prerequisites

- [minikube](https://minikube.sigs.k8s.io/docs/start/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- Docker
- An [Oodle](https://oodle.ai) account (instance ID and API key)

## Quick Start

```bash
make help
```

1. Copy the environment file and add your Oodle credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your OODLE_INSTANCE and OODLE_API_KEY
   ```

2. Deploy everything (starts minikube, installs operator, builds apps, deploys):
   ```bash
   make up
   ```

3. Traces appear automatically in Oodle — the load generator sends requests every 3 seconds.

## Step-by-Step Setup

If you prefer to run each step individually:

```bash
# 1. Start minikube + install cert-manager + OTel Operator
make setup

# 2. Build app container images inside minikube
make build

# 3. Create the Oodle credentials secret
make secret

# 4. Deploy the OTel Collector and Instrumentation CRDs
make deploy-operator

# 5. Deploy the application services and load generator
make deploy-apps
```

## Operations

```bash
make status          # Pod, deployment, service, and OTel resource status
make logs            # Tail all pod logs
make logs-collector  # Tail collector logs (check for export errors)
make logs-frontend   # Tail frontend logs
make test            # Send a manual test order
make restart-apps    # Restart apps (re-triggers instrumentation injection)
```

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **Traces**
3. Filter by service name: `frontend`, `order-service`, or `payment-service`
4. Click a trace to see the span waterfall across Node.js, Python, and Java services

## OTel Operator Resources

### OpenTelemetryCollector (`k8s/collector.yaml`)

Deploys a collector instance managed by the operator. The collector:
- Receives OTLP on ports 4317 (gRPC) and 4318 (HTTP)
- Exports to Oodle via OTLP/HTTP with API key authentication
- Reads credentials from a Kubernetes Secret

### Instrumentation (`k8s/instrumentation.yaml`)

Configures auto-instrumentation injection. The operator uses this to:
- Set the OTLP exporter endpoint for injected SDKs
- Configure context propagation (W3C tracecontext + baggage)
- Set sampling to 100% (all traces captured)

## Cleanup

```bash
# Remove app namespace only (keeps operator installed for re-use)
make down

# Remove everything (operator, cert-manager, namespace)
make clean
```

## Troubleshooting

### Pods stuck in Init

The operator injects an init container to install the OTel SDK. If it's stuck:
```bash
kubectl describe pod <pod-name> -n otel-demo
kubectl logs <pod-name> -n otel-demo -c opentelemetry-auto-instrumentation
```

### No traces in Oodle

1. Check collector logs for export errors:
   ```bash
   make logs-collector
   ```

2. Verify the secret has correct values:
   ```bash
   kubectl get secret oodle-credentials -n otel-demo -o jsonpath='{.data.instance}' | base64 -d
   ```

3. Verify the Instrumentation CR is applied:
   ```bash
   kubectl get instrumentation -n otel-demo
   ```

4. Check that pods have the auto-instrumentation init container:
   ```bash
   kubectl get pod <pod-name> -n otel-demo -o jsonpath='{.spec.initContainers[*].name}'
   ```

### Operator not running

```bash
kubectl get pods -n opentelemetry-operator-system
kubectl logs -n opentelemetry-operator-system -l app.kubernetes.io/name=opentelemetry-operator
```

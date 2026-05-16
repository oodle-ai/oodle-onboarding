# Kubernetes Deployment - Tracing Demo

Deploy the distributed tracing demo on Kubernetes using plain manifests and Kustomize.

## Architecture

```
load-generator --> frontend-api --> java-service --> python-service
                                \-> go-service   --> python-service
```

## Prerequisites

- `kubectl` configured with a running cluster (minikube, kind, EKS, GKE, etc.)
- Docker for building images

## 1. Build Images

From the `tracing-demo/` directory:

```bash
docker build -t tracing-demo/frontend-api:latest ./frontend-api/
docker build -t tracing-demo/java-service:latest ./java-service/
docker build -t tracing-demo/python-service:latest ./python-service/
docker build -t tracing-demo/go-service:latest ./go-service/
docker build -t tracing-demo/load-generator:latest ./load-generator/
```

## 2. Load Images into Your Cluster

**minikube:**
```bash
# Option A: Build directly inside minikube's Docker
eval $(minikube docker-env)
# Then re-run the docker build commands above

# Option B: Load pre-built images
minikube image load tracing-demo/frontend-api:latest
minikube image load tracing-demo/java-service:latest
minikube image load tracing-demo/python-service:latest
minikube image load tracing-demo/go-service:latest
minikube image load tracing-demo/load-generator:latest
```

**kind:**
```bash
kind load docker-image tracing-demo/frontend-api:latest
kind load docker-image tracing-demo/java-service:latest
kind load docker-image tracing-demo/python-service:latest
kind load docker-image tracing-demo/go-service:latest
kind load docker-image tracing-demo/load-generator:latest
```

## 3. Deploy

```bash
kubectl apply -k k8s/
```

## 4. Verify

```bash
# Check all pods are running
kubectl get pods -n tracing-demo

# Watch pods come up
kubectl get pods -n tracing-demo -w
```

Expected output (all pods Running, 1/1 Ready):
```
NAME                              READY   STATUS    RESTARTS   AGE
frontend-api-xxx                  1/1     Running   0          60s
go-service-xxx                    1/1     Running   0          60s
java-service-xxx                  1/1     Running   0          60s
load-generator-xxx                1/1     Running   0          60s
python-service-xxx                1/1     Running   0          60s
```

> Note: `java-service` may take 15-30s to become Ready due to JVM warm-up.

## 5. Access the Demo

```bash
# Port-forward the frontend API
kubectl port-forward -n tracing-demo svc/frontend-api 8080:8080

# Send a test request
curl -X POST http://localhost:8080/order -H 'Content-Type: application/json' -d '{"item":"widget","quantity":2}'
```

The load generator automatically sends requests every 3 seconds.

## 6. View Logs

```bash
kubectl logs -n tracing-demo -l app=frontend-api
kubectl logs -n tracing-demo -l app=java-service
kubectl logs -n tracing-demo -l app=python-service
kubectl logs -n tracing-demo -l app=go-service
kubectl logs -n tracing-demo -l app=load-generator
```

## 7. Teardown

```bash
kubectl delete -k k8s/
```

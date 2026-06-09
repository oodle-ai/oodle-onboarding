-include .env
export

NAMESPACE := otel-demo
CERT_MANAGER_VERSION := v1.17.2

.PHONY: help setup install-cert-manager install-operator build secret deploy-operator deploy-apps up down logs status test clean

help:
	@echo "OTel Operator Demo (minikube)"
	@echo ""
	@echo "Full setup:"
	@echo "  make up              - Complete setup: minikube + operator + build + deploy"
	@echo "  make down            - Delete app namespace (keeps operator installed)"
	@echo "  make clean           - Delete everything including operator and cert-manager"
	@echo ""
	@echo "Step-by-step:"
	@echo "  make setup           - Start minikube + install cert-manager + OTel Operator"
	@echo "  make build           - Build app images in minikube"
	@echo "  make secret          - Create Oodle credentials secret"
	@echo "  make deploy-operator - Deploy collector + instrumentation CRDs"
	@echo "  make deploy-apps     - Deploy app workloads + load generator"
	@echo ""
	@echo "Operations:"
	@echo "  make logs            - Tail all pod logs in namespace"
	@echo "  make logs-collector  - Tail OTel Collector logs"
	@echo "  make logs-frontend   - Tail frontend logs"
	@echo "  make status          - Show pod and deployment status"
	@echo "  make test            - Send a test order request"
	@echo "  make restart-apps    - Restart app deployments (re-triggers injection)"

# ---------- Full lifecycle ----------

up: setup build secret deploy-operator deploy-apps
	@echo ""
	@echo "All deployed. Traces should appear in Oodle within a few minutes."
	@echo "Run 'make status' to check pod readiness."
	@echo "Run 'make test' to send a manual request."

down:
	kubectl delete namespace $(NAMESPACE) --ignore-not-found

clean: down
	kubectl delete -f https://github.com/open-telemetry/opentelemetry-operator/releases/latest/download/opentelemetry-operator.yaml --ignore-not-found
	kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/$(CERT_MANAGER_VERSION)/cert-manager.yaml --ignore-not-found

# ---------- Setup steps ----------

setup: install-cert-manager install-operator
	@echo "Minikube and OTel Operator ready."

install-cert-manager:
	@minikube status > /dev/null 2>&1 || minikube start --memory=4096
	@echo "Installing cert-manager $(CERT_MANAGER_VERSION)..."
	kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/$(CERT_MANAGER_VERSION)/cert-manager.yaml
	@echo "Waiting for cert-manager..."
	kubectl wait --for=condition=Available deployment --all -n cert-manager --timeout=180s

install-operator:
	@echo "Installing OpenTelemetry Operator..."
	kubectl apply -f https://github.com/open-telemetry/opentelemetry-operator/releases/latest/download/opentelemetry-operator.yaml
	@echo "Waiting for OTel Operator..."
	kubectl wait --for=condition=Available deployment --all -n opentelemetry-operator-system --timeout=180s

# ---------- Build ----------

build:
	@echo "Building images inside minikube..."
	eval $$(minikube docker-env) && docker build -t otel-demo/frontend:latest apps/frontend/
	eval $$(minikube docker-env) && docker build -t otel-demo/order-service:latest apps/order-service/
	eval $$(minikube docker-env) && docker build -t otel-demo/payment-service:latest apps/payment-service/
	eval $$(minikube docker-env) && docker build -t otel-demo/load-generator:latest apps/load-generator/

# ---------- Deploy ----------

secret:
	@test -n "$(OODLE_INSTANCE)" || (echo "Error: OODLE_INSTANCE not set. Copy .env.example to .env and fill in values." && exit 1)
	@test -n "$(OODLE_API_KEY)" || (echo "Error: OODLE_API_KEY not set. Copy .env.example to .env and fill in values." && exit 1)
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic oodle-credentials \
		--from-literal=instance=$(OODLE_INSTANCE) \
		--from-literal=api-key=$(OODLE_API_KEY) \
		-n $(NAMESPACE) \
		--dry-run=client -o yaml | kubectl apply -f -

deploy-operator:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/collector.yaml
	kubectl apply -f k8s/instrumentation.yaml
	@echo "Waiting for collector pod..."
	kubectl wait --for=condition=Available deployment/oodle-collector -n $(NAMESPACE) --timeout=120s

deploy-apps:
	kubectl apply -f k8s/deployment-order-service.yaml
	kubectl apply -f k8s/service-order-service.yaml
	kubectl apply -f k8s/deployment-payment-service.yaml
	kubectl apply -f k8s/service-payment-service.yaml
	kubectl apply -f k8s/deployment-frontend.yaml
	kubectl apply -f k8s/service-frontend.yaml
	kubectl apply -f k8s/deployment-load-generator.yaml
	@echo "Waiting for apps to be ready..."
	kubectl wait --for=condition=Available deployment --all -n $(NAMESPACE) --timeout=180s

restart-apps:
	kubectl rollout restart deployment/frontend deployment/order-service deployment/payment-service -n $(NAMESPACE)

# ---------- Operations ----------

logs:
	kubectl logs -n $(NAMESPACE) -l app --all-containers -f --max-log-requests=10

logs-collector:
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=oodle-collector -f

logs-frontend:
	kubectl logs -n $(NAMESPACE) -l app=frontend -f

status:
	@echo "=== Pods ==="
	kubectl get pods -n $(NAMESPACE) -o wide
	@echo ""
	@echo "=== Deployments ==="
	kubectl get deployments -n $(NAMESPACE)
	@echo ""
	@echo "=== Services ==="
	kubectl get services -n $(NAMESPACE)
	@echo ""
	@echo "=== OTel Resources ==="
	kubectl get opentelemetrycollectors,instrumentations -n $(NAMESPACE)

test:
	@echo "Sending test order..."
	kubectl run curl-test --rm -i --restart=Never --image=curlimages/curl -n $(NAMESPACE) -- \
		curl -s -X POST http://frontend:3000/order \
		-H 'Content-Type: application/json' \
		-d '{"item":"widget","quantity":5}'

.PHONY: up down logs logs-alloy clean restart test status help

help: ## Show this help
	@echo "Datadog Alloy Single-Write Demo (Grafana Alloy -> Oodle via Datadog intake)"
	@echo ""
	@echo "Usage:"
	@echo "  make up          - Build and start all services"
	@echo "  make down        - Stop all services"
	@echo "  make logs        - View demo app logs"
	@echo "  make logs-alloy  - View Alloy logs"
	@echo "  make test        - Send sample requests"
	@echo "  make status      - Show running containers"
	@echo "  make restart     - Restart all services"
	@echo "  make clean       - Stop and remove volumes"

up: ## Build and start all services
	docker-compose up --build -d

down: ## Stop all services
	docker-compose down

logs: ## View demo app logs
	docker-compose logs -f demo-app

logs-alloy: ## View Alloy logs
	docker-compose logs -f alloy

status: ## Show running containers
	docker-compose ps

restart: down up ## Restart all services

test: ## Send sample requests to generate traces and metrics
	@echo "==> Sending requests to generate traces..."
	@for i in 1 2 3 4 5; do \
		curl -s -X POST http://localhost:8080/api/order | python3 -m json.tool 2>/dev/null || true; \
		curl -s http://localhost:8080/api/users | python3 -m json.tool 2>/dev/null || true; \
	done
	@echo ""
	@echo "==> Done. Check Oodle for service 'alloy-oodle-demo':"
	@echo "    Traces:  dd_trace_span metrics and APM traces"
	@echo "    Alloy UI: http://localhost:12345"

clean: ## Stop and remove volumes
	docker-compose down -v

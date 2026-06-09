.PHONY: up down logs logs-agent clean restart test status help

help: ## Show this help
	@echo "Datadog Dual-Write Demo (Datadog + Oodle)"
	@echo ""
	@echo "Usage:"
	@echo "  make up       - Build and start all services"
	@echo "  make down     - Stop all services"
	@echo "  make logs     - View demo app logs"
	@echo "  make logs-agent - View Datadog Agent logs"
	@echo "  make test     - Send sample requests"
	@echo "  make status   - Show running containers"
	@echo "  make restart  - Restart all services"
	@echo "  make clean    - Stop and remove volumes"

up: ## Build and start all services
	docker-compose up --build -d

down: ## Stop all services
	docker-compose down

logs: ## View demo app logs
	docker-compose logs -f demo-app

logs-agent: ## View Datadog Agent logs
	docker-compose logs -f datadog-agent

status: ## Show running containers
	docker-compose ps

restart: down up ## Restart all services

test: ## Send sample requests to generate traces and metrics
	@echo "==> Sending requests to generate traces and custom metrics..."
	@for i in 1 2 3 4 5; do \
		curl -s -X POST http://localhost:8080/api/order | python3 -m json.tool 2>/dev/null || true; \
		curl -s http://localhost:8080/api/users | python3 -m json.tool 2>/dev/null || true; \
	done
	@echo ""
	@echo "==> Done. Check both UIs:"
	@echo "    Datadog APM:     https://app.datadoghq.com/apm/traces"
	@echo "    Datadog Metrics: https://app.datadoghq.com/metric/explorer"
	@echo "    Oodle:           https://app-dev.oodle.ai"

clean: ## Stop and remove volumes
	docker-compose down -v

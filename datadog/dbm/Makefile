.PHONY: up down logs logs-agent logs-workload logs-postgres clean restart status help psql

help: ## Show this help
	@echo "Datadog Database Monitoring Demo (Oodle only)"
	@echo ""
	@echo "Usage:"
	@echo "  make up            - Start all services"
	@echo "  make down          - Stop all services"
	@echo "  make logs          - View all logs"
	@echo "  make logs-agent    - View Datadog Agent logs"
	@echo "  make logs-workload - View workload generator logs"
	@echo "  make logs-postgres - View PostgreSQL logs"
	@echo "  make psql          - Open psql shell"
	@echo "  make status        - Show running containers"
	@echo "  make restart       - Restart all services"
	@echo "  make clean         - Stop and remove volumes"

up: ## Start all services
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## View all logs
	docker compose logs -f

logs-agent: ## View Datadog Agent logs
	docker compose logs -f datadog-agent

logs-workload: ## View workload generator logs
	docker compose logs -f workload

logs-postgres: ## View PostgreSQL logs
	docker compose logs -f orders-db analytics-db inventory-db

psql: ## Open psql shell (orders-db)
	docker compose exec orders-db psql -U postgres -d orders

status: ## Show running containers
	docker compose ps

restart: down up ## Restart all services

clean: ## Stop and remove volumes
	docker compose down -v

.PHONY: help build up down logs logs-app logs-collector \
	test-order test-reject test-error test-all clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build containers
	docker compose build

up: ## Start all services
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Tail all logs
	docker compose logs -f

logs-app: ## Tail app logs
	docker compose logs -f app

logs-collector: ## Tail collector logs
	docker compose logs -f otel-collector

test-order: ## Place an order (info + debug lines)
	@curl -s -X POST 'http://localhost:8100/order?sku=sku-200&qty=2' \
		| python3 -m json.tool

test-reject: ## Rejected orders (warn lines)
	@curl -s -X POST 'http://localhost:8100/order?sku=sku-999' \
		| python3 -m json.tool
	@curl -s -X POST 'http://localhost:8100/order?sku=sku-100&qty=50' \
		| python3 -m json.tool

test-error: ## A failing request (error line with a stack)
	@curl -s 'http://localhost:8100/crash' | python3 -m json.tool

test-all: ## Run all test requests
	@echo "=== Order ===" && $(MAKE) test-order
	@echo "\n=== Rejected ===" && $(MAKE) test-reject
	@echo "\n=== Error ===" && $(MAKE) test-error

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

.PHONY: help build up down logs logs-app logs-collector \
	test-chat test-tool test-all clean

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

test-chat: ## One model call, no tools
	@curl -s -X POST http://localhost:8096/chat \
		-H 'Content-Type: application/json' \
		-d '{"message": "Name one fact about Helsinki."}' \
		| python3 -m json.tool

test-tool: ## Two model calls around one tool execution
	@curl -s -X POST http://localhost:8096/tool-call \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is the weather in Helsinki?"}' \
		| python3 -m json.tool

test-all: ## Run all test requests
	@echo "=== Chat ===" && $(MAKE) test-chat
	@echo "\n=== Tool call ===" && $(MAKE) test-tool

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

.PHONY: help build up down logs logs-app logs-collector \
	test-generate test-agent test-all clean

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

test-generate: ## One model call, no tools
	@curl -s -X POST http://localhost:8097/generate \
		-H 'Content-Type: application/json' \
		-d '{"prompt": "Name one fact about Reykjavik."}' \
		| python3 -m json.tool

test-agent: ## Multi-step agent run with tool calls
	@curl -s -X POST http://localhost:8097/agent \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is the weather in Lisbon and what should I do there?"}' \
		| python3 -m json.tool

test-all: ## Run all test requests
	@echo "=== Generate ===" && $(MAKE) test-generate
	@echo "\n=== Agent ===" && $(MAKE) test-agent

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

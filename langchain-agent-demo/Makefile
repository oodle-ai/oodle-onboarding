.PHONY: help up down logs logs-app logs-collector \
	test-chat test-trip test-research \
	test-multi clean build

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

test-chat: ## Send a chat request
	@curl -s -X POST http://localhost:8092/chat \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is the weather in Tokyo?"}' \
		| python3 -m json.tool

test-trip: ## Plan a trip (ReAct agent with tools)
	@curl -s -X POST 'http://localhost:8092/plan-trip?city=Paris&days=3&style=moderate' \
		| python3 -m json.tool

test-research: ## Research a city (multi-tool agent)
	@curl -s -X POST 'http://localhost:8092/research?city=Tokyo' \
		| python3 -m json.tool

test-multi: ## Multi-agent workflow (research + plan)
	@curl -s -X POST 'http://localhost:8092/multi-agent?city=Tokyo' \
		| python3 -m json.tool

test-all: ## Run all test requests
	@echo "=== Chat ===" && $(MAKE) test-chat
	@echo "\n=== Trip Plan ===" && $(MAKE) test-trip
	@echo "\n=== Research ===" && $(MAKE) test-research
	@echo "\n=== Multi-Agent ===" && $(MAKE) test-multi

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

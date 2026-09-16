.PHONY: help build up down logs logs-app logs-app-ts logs-collector \
	test-chat test-trip test-chat-ts test-all clean

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

logs-app-ts: ## Tail LangGraph.js app logs
	docker compose logs -f app-ts

logs-collector: ## Tail collector logs
	docker compose logs -f otel-collector

test-chat: ## ReAct loop with tool calls
	@curl -s -X POST 'http://localhost:8099/chat?message=What%20is%20the%20weather%20in%20Tokyo%20right%20now%3F' \
		| python3 -m json.tool

test-trip: ## Two-node pipeline: research, then plan
	@curl -s -X POST 'http://localhost:8099/plan-trip?city=Paris' \
		| python3 -m json.tool

test-chat-ts: ## ReAct loop with tool calls (LangGraph.js)
	@curl -s -X POST 'http://localhost:8101/chat?message=What%20is%20the%20weather%20in%20London%3F' \
		| python3 -m json.tool

test-all: ## Run all test requests
	@echo "=== Chat ===" && $(MAKE) test-chat
	@echo "\n=== Trip plan ===" && $(MAKE) test-trip
	@echo "\n=== Chat (LangGraph.js) ===" && $(MAKE) test-chat-ts

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

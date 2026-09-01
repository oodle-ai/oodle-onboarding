.PHONY: help build up down logs logs-agent logs-collector \
	test-chat test-followup test-all clean

THREAD ?= demo-thread

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

logs-agent: ## Tail agent logs
	docker compose logs -f agent

logs-collector: ## Tail collector logs
	docker compose logs -f otel-collector

test-chat: ## Send a message that calls both tools
	@curl -s -X POST http://localhost:8098/chat/$(THREAD) \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is the weather in Lisbon, and what should I do there?"}' \
		| python3 -m json.tool

test-followup: ## Send a second turn on the same thread
	@curl -s -X POST http://localhost:8098/chat/$(THREAD) \
		-H 'Content-Type: application/json' \
		-d '{"message": "And in Tokyo?"}' \
		| python3 -m json.tool

test-all: ## Run a two-turn conversation
	@echo "=== Turn 1 ===" && $(MAKE) test-chat
	@echo "\n=== Turn 2 ===" && $(MAKE) test-followup

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

.PHONY: help build up down logs logs-agent logs-collector \
	test-chat test-followup test-unknown test-all clean

THREAD ?= demo-trip
CHAT = docker compose exec -T agent node scripts/chat.mjs $(THREAD)

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

test-chat: ## One turn: two tools and a packing subagent
	@$(CHAT) "Plan a day in Lisbon."

test-followup: ## Second turn on the same conversation
	@$(CHAT) "And what about Tokyo?"

test-unknown: ## A city with no forecast: the tool result carries an error
	@$(CHAT) "Plan a day in Atlantis."

test-all: ## Run a three-turn conversation
	@echo "=== Turn 1 ===" && $(MAKE) --no-print-directory test-chat
	@echo "\n=== Turn 2 ===" && $(MAKE) --no-print-directory test-followup
	@echo "\n=== Turn 3 ===" && $(MAKE) --no-print-directory test-unknown

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

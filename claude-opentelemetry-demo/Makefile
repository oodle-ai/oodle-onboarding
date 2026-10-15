.PHONY: help build up down logs-collector destination-create destination-list \
	messages-api sdk managed-agents-setup managed-agents all clean

RUN = docker compose run --rm

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

build: ## Build the three sub-demo images
	docker compose --profile demo build

up: ## Start the OTel Collector (forwards SDK and app spans to Oodle)
	docker compose up -d otel-collector

down: ## Stop everything
	docker compose --profile demo down

logs-collector: ## Tail the collector (debug exporter prints each span)
	docker compose logs -f otel-collector

destination-create: ## API tracing: add Oodle as a telemetry destination (org admin)
	./scripts/create-destination.sh

destination-list: ## API tracing: list destinations and their delivery health
	./scripts/list-destinations.sh

messages-api: up ## Sub-demo 1: Messages API over plain HTTP (needs the destination)
	$(RUN) --build messages-api

sdk: up ## Sub-demo 2: Python SDK tracing
	$(RUN) --build claude-sdk

managed-agents-setup: ## Sub-demo 3, once: create the agent and environment
	$(RUN) --build --no-deps managed-agents provision.py

managed-agents: up ## Sub-demo 3: run a Managed Agents session
	$(RUN) --build managed-agents

all: sdk messages-api managed-agents ## Run all three sub-demos

clean: ## Stop and remove containers, networks and volumes
	docker compose --profile demo down -v --remove-orphans

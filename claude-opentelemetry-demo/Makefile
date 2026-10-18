.PHONY: help build up down logs-collector destination-create destination-list \
	messages-api sdk managed-agents-setup managed-agents managed-agents-logs mcp-backend-setup \
	mcp-backend mcp-backend-logs all clean

RUN = docker compose run --rm

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

build: ## Build the sub-demo images
	docker compose --profile demo --profile mcp build

up: ## Start the OTel Collector (forwards SDK and app spans to Oodle)
	docker compose up -d otel-collector

down: ## Stop everything, the tunnel too
	docker compose --profile demo --profile mcp down

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

managed-agents: up ## Sub-demo 3: run a Managed Agents session (starts the warehouse)
	docker compose --profile demo up -d --build --wait warehouse
	$(RUN) --build managed-agents

managed-agents-logs: ## Sub-demo 3: tail the warehouse service
	docker compose --profile demo logs -f warehouse

mcp-backend-setup: ## Sub-demo 4, once: create an environment that allows MCP egress
	$(RUN) --build --no-deps -e DEMO_ROLE=provision mcp-backend

mcp-backend: up ## Sub-demo 4: backend + MCP server + managed agent (needs the destination)
	docker compose --profile mcp up -d --build mcp-mariadb mcp-web mcp-tunnel mcp-app
	$(RUN) --build mcp-backend

mcp-backend-logs: ## Sub-demo 4: tail the backend, the MCP server and the tunnel
	docker compose --profile mcp logs -f mcp-app mcp-web mcp-tunnel

all: sdk messages-api managed-agents ## Run the first three sub-demos

clean: ## Stop and remove containers, networks and volumes
	docker compose --profile demo --profile mcp down -v --remove-orphans

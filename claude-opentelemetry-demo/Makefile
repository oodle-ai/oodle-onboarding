.PHONY: help build up down logs-collector destination-create destination-list \
	messages-api sdk managed-agents-setup managed-agents managed-agents-incident managed-agents-fix \
	managed-agents-mcp-incident managed-agents-mcp-fix managed-agents-logs mcp-backend-setup \
	mcp-backend mcp-backend-logs all clean

RUN = docker compose run --rm
MARIADB = docker compose --profile mcp exec -T mcp-mariadb mariadb -ulxuser -plxpass
MCP_TASK = Use the firm-mcp server with orgid 54. List the firm's people with their roles and its past \
	projects, then tell me who should lead a new water project and why.

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

managed-agents-incident: up ## Sub-demo 3: break apac-orders, then run a session (a wrong answer, all green)
	docker compose --profile demo build managed-agents
	docker compose --profile demo up -d --build --wait warehouse
	docker compose --profile demo exec apac-orders python migrate.py drop-index
	@# --no-deps: `run` would otherwise recreate apac-orders, which brings the index back.
	$(RUN) --no-deps managed-agents

managed-agents-fix: ## Sub-demo 3: undo the incident
	docker compose --profile demo exec apac-orders python migrate.py restore-index

managed-agents-mcp-incident: ## Sub-demo 3: break an MCP tool, then run a session (needs the tunnel and MCP_TRACE_CONTEXT=true)
	@docker compose --profile mcp exec -T mcp-web sh -c 'test "$$MCP_TRACE_CONTEXT" = true' \
		|| (echo "Set MCP_TRACE_CONTEXT=true in .env and recreate mcp-web."; exit 1)
	$(MARIADB) -e "ALTER TABLE meta_db.org_54_employees CHANGE COLUMN IF EXISTS role job_title VARCHAR(255)"
	$(RUN) --no-deps managed-agents main.py "$(MCP_TASK)"

managed-agents-mcp-fix: ## Sub-demo 3: undo the MCP incident
	$(MARIADB) -e "ALTER TABLE meta_db.org_54_employees CHANGE COLUMN IF EXISTS job_title role VARCHAR(255)"

managed-agents-logs: ## Sub-demo 3: tail the warehouse and apac-orders
	docker compose --profile demo logs -f warehouse apac-orders

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

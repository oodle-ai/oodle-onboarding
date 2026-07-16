# Deploy the Datadog Agent host-local daemon (APM + DogStatsD + process agent) and
# point the Rails demo app at it. Convox global flags go AFTER the subcommand.

-include .env

RACK           ?= org-team-i4e/gm-test
APP            ?= datadog-agent
TARGET_APP     ?= rails-demo
APM_PORT       ?= 8126
# Docker default bridge gateway on the ECS-optimized AMI — from inside a bridge
# app container this routes to the host, where the agent publishes 8126/8125.
BRIDGE_GATEWAY ?= 172.17.0.1

.DEFAULT_GOAL := help
.PHONY: help up create deploy deploy-app logs ps status down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: create deploy ## Create the agent app, set secrets, deploy the daemon (does NOT touch any app yet)

# Oodle single-shipping endpoints (metrics + traces), built from .env. Oodle is the PRIMARY
# intake — the DD Agent sends to these ONLY (nothing to Datadog). Per the Oodle Datadog
# integration tile (single-shipping, Datadog Agent): dd_url + Oodle api_key for metrics,
# apm_dd_url for traces. Valued via `convox env` (declared, not valued, in convox.yml).
OODLE_METRICS_URL = https://$(OODLE_COLLECTOR_DOMAIN)/v1/datadog/$(OODLE_INSTANCE_ID)
OODLE_TRACES_URL  = https://$(OODLE_COLLECTOR_DOMAIN)/v1/datadog_traces/$(OODLE_INSTANCE_ID)

create: ## Create the agent app (no-op if it exists) and set the Oodle single-shipping secrets
	@convox apps create $(APP) -r $(RACK) 2>/dev/null || echo "app $(APP) already exists"
	@test -n "$(OODLE_API_KEY)" || { echo "Set OODLE_API_KEY/OODLE_COLLECTOR_DOMAIN/OODLE_INSTANCE_ID (copy .env.example to .env)"; exit 1; }
	convox env set DD_API_KEY=$(OODLE_API_KEY) \
		DD_DD_URL=$(OODLE_METRICS_URL) \
		DD_APM_DD_URL=$(OODLE_TRACES_URL) \
		-a $(APP) -r $(RACK)
	@# Clear stale dual-write vars from a prior dual-shipping deploy (harmless if absent).
	-@convox env unset DD_SITE DD_ADDITIONAL_ENDPOINTS DD_APM_ADDITIONAL_ENDPOINTS -a $(APP) -r $(RACK) 2>/dev/null || true

deploy: ## Build & deploy the agent (must be running BEFORE apps send traces to it)
	convox deploy -a $(APP) -r $(RACK)

# NOTE: the Rails app's tracer env (DD_AGENT_HOST=172.17.0.1, DD_SERVICE, DD_ENV, ...) is
# declared in the repo-root convox.yml `environment:` block — NOT set via `convox env set`.
# Convox only injects env vars a service's manifest DECLARES; `convox env set`-only vars are
# stored but never reach the container (that's why the tracer silently used 127.0.0.1 and
# dropped every span until the vars were added to convox.yml). To retarget, edit convox.yml.
deploy-app: ## Rebuild & deploy the Rails app so it picks up the `datadog` gem + tracer env (runs from repo root)
	cd .. && convox deploy -a $(TARGET_APP) -r $(RACK)

logs: ## Tail the agent's own logs (set DD_LOG_LEVEL=info in convox.yml first to see detail)
	convox logs -a $(APP) -r $(RACK)

ps: ## Show agent processes (expect one per rack instance)
	convox ps -a $(APP) -r $(RACK)

status: ## Run `agent status` inside a running agent (verify APM receiver + trace flow)
	@pid=$$(convox ps -a $(APP) -r $(RACK) | awk 'NR==2{print $$1}'); \
		echo "exec into $$pid"; convox exec $$pid "agent status" -a $(APP) -r $(RACK)

down: ## Delete the agent app (scale-0 does NOT stop a DaemonSet agent)
	convox apps delete $(APP) -r $(RACK)

clean: down ## Alias for down

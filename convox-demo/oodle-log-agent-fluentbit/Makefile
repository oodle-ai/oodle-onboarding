# Deploy the Fluent Bit host-local log agent (per-app routing via ECS introspection).
# Runs ALONGSIDE the OTel agent (port 5141 vs 5140). Convox global flags go AFTER the subcommand.

-include .env

RACK        ?= org-team-i4e/gm-test
APP         ?= oodle-log-agent-fb
TARGET_APP  ?= rails-demo
FB_PORT     ?= 5141
OTEL_PORT   ?= 5140
RACK_PREFIX ?= gm-test
REGION      ?= us-east-1
# AWS managed policy granting CloudWatch Logs create/put (for the cloudwatch_logs output).
IAM_POLICY  ?= arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

.DEFAULT_GOAL := help
.PHONY: help up create iam deploy switch-rails restore-otel logs ps down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: create iam deploy ## Create app, grant IAM, deploy the Fluent Bit agent (does NOT switch rails-demo)

create: ## Create the agent app (no-op if it exists) and set env
	@convox apps create $(APP) -r $(RACK) 2>/dev/null || echo "app $(APP) already exists"
	@test -n "$(OODLE_INSTANCE)" && test -n "$(OODLE_API_KEY)" || \
		{ echo "Set OODLE_INSTANCE and OODLE_API_KEY (copy .env.example to .env)"; exit 1; }
	convox env set OODLE_INSTANCE=$(OODLE_INSTANCE) OODLE_API_KEY=$(OODLE_API_KEY) RACK_PREFIX=$(RACK_PREFIX) -a $(APP) -r $(RACK)

iam: ## Grant the agent task role CloudWatch Logs write access
	convox apps params set IamPolicy=$(IAM_POLICY) -a $(APP) -r $(RACK)

deploy: ## Build & deploy the agent (must be running BEFORE pointing an app at it)
	convox deploy -a $(APP) -r $(RACK)

switch-rails: ## Point rails-demo's logs at the Fluent Bit agent (port 5141) — the validation step
	convox apps params set LogDriver=Syslog SyslogDestination=tcp://localhost:$(FB_PORT) SyslogFormat=rfc5424 \
		-a $(TARGET_APP) -r $(RACK)

restore-otel: ## Point rails-demo back at the OTel agent (port 5140), restoring the prior dual-write
	convox apps params set LogDriver=Syslog SyslogDestination=tcp://localhost:$(OTEL_PORT) SyslogFormat=rfc5424 \
		-a $(TARGET_APP) -r $(RACK)

logs: ## Tail the Fluent Bit agent's own logs (shows enriched records via the debug stdout output)
	convox logs -a $(APP) -r $(RACK)

ps: ## Show agent processes (expect one per rack instance)
	convox ps -a $(APP) -r $(RACK)

down: restore-otel ## Point rails-demo back to the OTel agent, then scale this agent to 0
	convox scale collector --count 0 -a $(APP) -r $(RACK)

clean: restore-otel ## Point rails-demo back to the OTel agent, then delete this agent app
	convox apps delete $(APP) -r $(RACK)

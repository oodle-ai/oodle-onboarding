# Deploy the Fluent Bit host-local log agent (per-app routing via ECS introspection).
# Convox global flags go AFTER the subcommand.

-include .env

RACK        ?= org-team-i4e/gm-test
APP         ?= oodle-log-agent
TARGET_APP  ?= rails-demo
SYSLOG_PORT ?= 5140
RACK_PREFIX ?= gm-test
REGION      ?= us-east-1
# AWS managed policy granting CloudWatch Logs create/put (dual-write phase only; drop for single-write).
IAM_POLICY  ?= arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

.DEFAULT_GOAL := help
.PHONY: help up create iam deploy retain-loggroup preserve-history enable-syslog disable-syslog logs ps down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: create iam deploy ## Create app, grant IAM, deploy the agent (does NOT switch any app's logs yet)

create: ## Create the agent app (no-op if it exists) and set env
	@convox apps create $(APP) -r $(RACK) 2>/dev/null || echo "app $(APP) already exists"
	@test -n "$(OODLE_INSTANCE)" && test -n "$(OODLE_API_KEY)" || \
		{ echo "Set OODLE_INSTANCE and OODLE_API_KEY (copy .env.example to .env)"; exit 1; }
	convox env set OODLE_INSTANCE=$(OODLE_INSTANCE) OODLE_API_KEY=$(OODLE_API_KEY) RACK_PREFIX=$(RACK_PREFIX) -a $(APP) -r $(RACK)

iam: ## Grant the agent task role CloudWatch Logs write access (dual-write phase; skip for single-write)
	convox apps params set IamPolicy=$(IAM_POLICY) -a $(APP) -r $(RACK)

deploy: ## Build & deploy the agent (must be running BEFORE pointing an app at it)
	convox deploy -a $(APP) -r $(RACK)

retain-loggroup: ## PRE-SWITCH, no-copy: delete-protect an app's managed CloudWatch group so the switch orphans it instead of deleting it (STACK=<rack>-<app>)
	@test -n "$(STACK)" || { echo "usage: make retain-loggroup STACK=<rack>-<app>  (e.g. gm-test-rails-demo)"; exit 1; }
	./retain-loggroup.sh $(STACK) $(REGION)

preserve-history: ## PRE-SWITCH, copy: copy an app's existing CloudWatch history into a persistent group (SRC=<managed-group> DST=<persistent-group>, e.g. DST=/convox/<app>)
	@test -n "$(SRC)" && test -n "$(DST)" || { echo "usage: make preserve-history SRC=<managed-group> DST=<persistent-group>"; exit 1; }
	./preserve-history.sh $(SRC) $(DST) $(REGION)

enable-syslog: ## Point an app's logs at this agent (per-app, not rack-wide); APP override: TARGET_APP=<app>
	convox apps params set LogDriver=Syslog SyslogDestination=tcp://localhost:$(SYSLOG_PORT) SyslogFormat=rfc5424 \
		-a $(TARGET_APP) -r $(RACK)

disable-syslog: ## Revert the app to native CloudWatch (restores `convox logs -a <app>`)
	convox apps params set LogDriver=CloudWatch SyslogDestination="" -a $(TARGET_APP) -r $(RACK)

logs: ## Tail the agent's own logs (shows enriched records via the debug stdout output)
	convox logs -a $(APP) -r $(RACK)

ps: ## Show agent processes (expect one per rack instance)
	convox ps -a $(APP) -r $(RACK)

down: disable-syslog ## Revert the app to CloudWatch, then delete this agent app (scale-0 doesn't stop a DaemonSet agent)
	convox apps delete $(APP) -r $(RACK)

clean: down ## Alias for down (revert the app, then delete the agent app)

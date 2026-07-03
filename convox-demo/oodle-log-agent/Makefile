# Deploy the host-local OTel log agent and switch rails-demo's logs to it.
# Convox global flags go AFTER the subcommand.

-include .env

RACK       ?= org-team-i4e/gm-test
APP        ?= oodle-log-agent
TARGET_APP ?= rails-demo
SYSLOG_PORT ?= 5140
REGION     ?= us-east-1
# AWS managed policy granting CloudWatch Logs create/put (for the awscloudwatchlogs exporter).
IAM_POLICY ?= arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

.DEFAULT_GOAL := help
.PHONY: help up create iam deploy enable-syslog disable-syslog logs ps down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: create iam deploy enable-syslog ## Full setup: create app, grant IAM, deploy agent, switch rails-demo to syslog

create: ## Create the agent app (no-op if it exists)
	@convox apps create $(APP) -r $(RACK) 2>/dev/null || echo "app $(APP) already exists"
	@test -n "$(OODLE_INSTANCE)" && test -n "$(OODLE_API_KEY)" || \
		{ echo "Set OODLE_INSTANCE and OODLE_API_KEY (copy .env.example to .env)"; exit 1; }
	convox env set OODLE_INSTANCE=$(OODLE_INSTANCE) OODLE_API_KEY=$(OODLE_API_KEY) -a $(APP) -r $(RACK)

iam: ## Grant the agent task role CloudWatch Logs write access
	convox apps params set IamPolicy=$(IAM_POLICY) -a $(APP) -r $(RACK)

deploy: ## Build & deploy the agent (must be running BEFORE enabling syslog)
	convox deploy -a $(APP) -r $(RACK)

preserve-history: ## Copy an app's existing CloudWatch history to a persistent group BEFORE switching (SRC=<managed-group> DST=<persistent-group>)
	@test -n "$(SRC)" && test -n "$(DST)" || { echo "usage: make preserve-history SRC=<managed-group> DST=<persistent-group>"; exit 1; }
	./preserve-history.sh $(SRC) $(DST) $(REGION)

enable-syslog: ## Point rails-demo's logs at the host-local agent (per-app, not rack-wide)
	convox apps params set LogDriver=Syslog SyslogDestination=tcp://localhost:$(SYSLOG_PORT) SyslogFormat=rfc5424 \
		-a $(TARGET_APP) -r $(RACK)

disable-syslog: ## Revert rails-demo to CloudWatch (restores `convox logs -a rails-demo`)
	convox apps params set LogDriver=CloudWatch SyslogDestination="" -a $(TARGET_APP) -r $(RACK)

logs: ## Tail the agent's own logs (agent stays on CloudWatch)
	convox logs -a $(APP) -r $(RACK)

ps: ## Show agent processes (expect one per rack instance)
	convox ps -a $(APP) -r $(RACK)

down: disable-syslog ## Revert rails-demo, then scale the agent to 0
	convox scale collector --count 0 -a $(APP) -r $(RACK)

clean: disable-syslog ## Revert rails-demo, then delete the agent app
	convox apps delete $(APP) -r $(RACK)

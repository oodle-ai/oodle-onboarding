# Deploy a sample Rails app to a Convox v2 (generation 2) rack.
# Override RACK / APP on the command line or via a local .env file.

-include .env

RACK ?= org-team-i4e/gm-test
APP  ?= rails-demo

# Convox global flags must come AFTER the subcommand (e.g. `convox deploy -a app -r rack`).
CXF := -a $(APP) -r $(RACK)

.DEFAULT_GOAL := help
.PHONY: help up create secret deploy logs url down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: create secret deploy url ## Create app (if needed), set secrets, build & deploy, print URL

create: ## Create the Convox app (no-op if it already exists)
	@convox apps create $(APP) -r $(RACK) 2>/dev/null || echo "app $(APP) already exists"

secret: ## Set SECRET_KEY_BASE if not already set
	@convox env $(CXF) | grep -q '^SECRET_KEY_BASE=' || \
		convox env set SECRET_KEY_BASE=$$(openssl rand -hex 64) $(CXF)

deploy: ## Build the image and promote a release
	convox deploy $(CXF)

logs: ## Tail application logs
	convox logs $(CXF)

url: ## Print the app's public endpoint
	@convox services $(CXF)

down: ## Stop the app (scale web to 0 — frees compute, keeps the app)
	convox scale web --count 0 $(CXF)

clean: ## Delete the Convox app entirely
	convox apps delete $(APP) -r $(RACK)

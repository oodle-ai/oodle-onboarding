.PHONY: help build run run-all laminar-up laminar-down laminar-logs clean

# The Laminar checkout. Gitignored; `make laminar-up` clones it.
LMNR_DIR ?= .lmnr

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build the agent image
	docker compose build

run: ## Run the session once with the TRACER from the environment
	docker compose run --rm agent

run-all: ## Run the session once per tracer
	@for t in litellm-otel laminar-to-oodle laminar; do \
		echo "=== TRACER=$$t ==="; \
		TRACER=$$t docker compose run --rm agent || exit 1; \
	done

laminar-up: ## Clone and start self-hosted Laminar (UI on :5667)
	@test -d $(LMNR_DIR) || git clone --depth 1 https://github.com/lmnr-ai/lmnr $(LMNR_DIR)
	cd $(LMNR_DIR) && docker compose up -d

laminar-down: ## Stop self-hosted Laminar
	cd $(LMNR_DIR) && docker compose down

laminar-logs: ## Tail Laminar's logs
	cd $(LMNR_DIR) && docker compose logs -f app-server

clean: ## Remove the agent image and the Laminar checkout
	docker compose down --rmi local --remove-orphans
	rm -rf $(LMNR_DIR)

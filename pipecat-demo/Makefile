.PHONY: help build up up-langfuse down logs verify-local clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

build: ## Build the container
	docker compose build

up: ## Start the voice bot, tracing over OpenTelemetry
	TRACING_BACKEND=otel docker compose up --build -d
	@echo "Open http://localhost:7860 and talk to the bot."

up-langfuse: ## Start the voice bot, tracing through the Langfuse SDK
	TRACING_BACKEND=langfuse-sdk docker compose up --build -d
	@echo "Open http://localhost:7860 and talk to the bot."

down: ## Stop the bot
	docker compose down

logs: ## Tail the bot's logs
	docker compose logs -f app

verify-local: ## Offline check of both paths against local receivers, no accounts needed
	docker compose run --rm --no-deps -T app python verify_local.py

clean: ## Stop and remove containers, volumes and the local image
	docker compose down -v --rmi local --remove-orphans

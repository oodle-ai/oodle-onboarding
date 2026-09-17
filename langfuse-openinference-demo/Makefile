.PHONY: help build run clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Build the container
	docker compose build

run: ## One planner run: one Langfuse generation around one instrumented OpenAI call
	docker compose run --rm app

clean: ## Remove the container and image
	docker compose down --rmi local

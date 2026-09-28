.PHONY: help build up down logs test-session test-all verify-local verify-local-no-mirror clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

build: ## Build containers
	docker compose build

up: ## Start the app
	docker compose up --build -d

down: ## Stop the app
	docker compose down

logs: ## Tail app logs
	docker compose logs -f app

test-session: ## Run one traced agent session
	@curl -s -X POST http://localhost:8102/session \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is in this repository?"}' \
		| python3 -m json.tool

test-all: test-session ## Run all test requests

verify-local: ## Offline check: both exports captured locally, no accounts needed
	docker compose run --rm --no-deps app python verify_local.py

verify-local-no-mirror: ## Same check with the mirror off (expect failures)
	docker compose run --rm --no-deps app python verify_local.py --no-mirror

clean: ## Stop and remove containers and volumes
	docker compose down -v --remove-orphans

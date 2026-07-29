.PHONY: help up down logs logs-app logs-collector \
	auth test-food test-grocery test-dineout test-combined \
	test-all clean build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build containers
	docker compose build

up: ## Start all services
	docker compose up --build -d

down: ## Stop all services
	docker compose down

logs: ## Tail all logs
	docker compose logs -f

logs-app: ## Tail app logs
	docker compose logs -f app

logs-collector: ## Tail collector logs
	docker compose logs -f otel-collector

auth: ## Run Swiggy OAuth flow (writes token to .env)
	python3 app/auth.py

test-food: ## Order food (biryani)
	@curl -s -X POST 'http://localhost:8094/order-food?query=biryani' \
		| python3 -m json.tool

test-grocery: ## Order groceries (milk)
	@curl -s -X POST 'http://localhost:8094/order-grocery?query=milk' \
		| python3 -m json.tool

test-dineout: ## Book a table (italian, 4 guests)
	@curl -s -X POST 'http://localhost:8094/book-table?query=italian&guests=4&date=2026-08-01' \
		| python3 -m json.tool

test-combined: ## Plan evening (dinner + dessert)
	@curl -s -X POST 'http://localhost:8094/plan-evening?dinner_query=italian&dessert_query=gelato&guests=4' \
		| python3 -m json.tool

test-all: ## Run all test requests
	@echo "=== Order Food ===" && $(MAKE) test-food
	@echo "\n=== Order Grocery ===" && $(MAKE) test-grocery
	@echo "\n=== Book Table ===" && $(MAKE) test-dineout
	@echo "\n=== Plan Evening ===" && $(MAKE) test-combined

clean: ## Stop services and remove volumes
	docker compose down -v --remove-orphans

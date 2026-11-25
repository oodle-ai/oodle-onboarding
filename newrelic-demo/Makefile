.PHONY: up down logs test status clean

up: ## Build and start everything
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api otel-collector inventory worker load

status:
	docker compose ps

test: ## One burst of requests
	@for i in $$(seq 1 5); do \
		curl -s -X POST http://localhost:8080/api/orders >/dev/null; \
		curl -s http://localhost:8080/api/products >/dev/null; \
		curl -s http://localhost:8080/api/orders/$$i >/dev/null; \
		curl -s http://localhost:8081/stock/$$i >/dev/null; \
	done; curl -s http://localhost:8080/api/stats; echo

clean:
	docker compose down -v

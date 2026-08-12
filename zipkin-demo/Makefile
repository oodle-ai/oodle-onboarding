.PHONY: up down logs logs-collector logs-app clean restart test status help
.PHONY: up-direct down-direct logs-direct clean-direct restart-direct

help:
	@echo "Zipkin Demo"
	@echo ""
	@echo "Via OTel Collector:"
	@echo "  make up              - Build and start all services"
	@echo "  make down            - Stop all services"
	@echo "  make logs            - View all logs"
	@echo "  make logs-collector  - View OTel Collector logs"
	@echo "  make logs-app        - View app logs"
	@echo "  make clean           - Stop and remove volumes"
	@echo "  make restart         - Restart all services"
	@echo ""
	@echo "Direct Ingestion (no collector):"
	@echo "  make up-direct       - Build and start app (direct to Oodle)"
	@echo "  make down-direct     - Stop app"
	@echo "  make logs-direct     - View app logs"
	@echo "  make clean-direct    - Stop and remove volumes"
	@echo "  make restart-direct  - Restart app"
	@echo ""
	@echo "Common:"
	@echo "  make test            - Send a test order request"
	@echo "  make status          - Show service status"

up:
	@echo "Starting all services..."
	docker-compose up --build -d

down:
	@echo "Stopping all services..."
	docker-compose down

logs:
	docker-compose logs -f

logs-collector:
	docker-compose logs -f otel-collector

logs-app:
	docker-compose logs -f app

clean:
	@echo "Cleaning up..."
	docker-compose down -v

restart: down up

up-direct:
	@echo "Starting app with direct ingestion..."
	docker-compose -f docker-compose.direct.yml up --build -d

down-direct:
	@echo "Stopping app..."
	docker-compose -f docker-compose.direct.yml down

logs-direct:
	docker-compose -f docker-compose.direct.yml logs -f

clean-direct:
	@echo "Cleaning up..."
	docker-compose -f docker-compose.direct.yml down -v

restart-direct: down-direct up-direct

test:
	@echo "Sending test order request..."
	curl -s -X POST http://localhost:8080/order \
		-H 'Content-Type: application/json' \
		-d '{"item":"gadget","quantity":2}' | python3 -m json.tool

status:
	docker-compose ps

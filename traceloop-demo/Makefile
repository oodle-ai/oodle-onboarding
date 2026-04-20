.PHONY: up down logs logs-collector logs-app clean restart test-chat test-summarize status help

help:
	@echo "Traceloop (OpenLLMetry) Demo"
	@echo ""
	@echo "Usage:"
	@echo "  make up              - Build and start all services"
	@echo "  make down            - Stop all services"
	@echo "  make logs            - View all logs"
	@echo "  make logs-collector  - View OTel Collector logs"
	@echo "  make logs-app        - View app logs"
	@echo "  make clean           - Stop and remove volumes"
	@echo "  make restart         - Restart all services"
	@echo "  make test-chat       - Send a test chat request"
	@echo "  make test-summarize  - Send a test summarize request"
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

test-chat:
	@echo "Sending test chat request..."
	curl -s -X POST http://localhost:8090/chat \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is OpenTelemetry in one sentence?"}' | python3 -m json.tool

test-summarize:
	@echo "Sending test summarize request..."
	curl -s -X POST http://localhost:8090/summarize \
		-H 'Content-Type: application/json' \
		-d '{"text": "OpenTelemetry is a collection of APIs, SDKs, and tools used to instrument, generate, collect, and export telemetry data (metrics, logs, and traces) to help you analyze your software performance and behavior. It is a CNCF project that provides a single set of APIs and libraries that standardize how you collect and transfer telemetry data. OpenTelemetry supports multiple programming languages and integrates with popular observability backends."}' | python3 -m json.tool

status:
	docker-compose ps

.PHONY: up down logs logs-collector logs-frontend logs-java logs-python logs-go logs-loadgen clean restart test status help

help:
	@echo "Tracing Demo"
	@echo ""
	@echo "Usage:"
	@echo "  make up              - Build and start all services"
	@echo "  make down            - Stop all services"
	@echo "  make logs            - View all logs"
	@echo "  make logs-collector  - View OTel Collector logs"
	@echo "  make logs-frontend   - View frontend-api logs"
	@echo "  make logs-java       - View java-service logs"
	@echo "  make logs-python     - View python-service logs"
	@echo "  make logs-go         - View go-service logs"
	@echo "  make logs-loadgen    - View load-generator logs"
	@echo "  make clean           - Stop and remove volumes"
	@echo "  make restart         - Restart all services"
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

logs-frontend:
	docker-compose logs -f frontend-api

logs-java:
	docker-compose logs -f java-service

logs-python:
	docker-compose logs -f python-service

logs-go:
	docker-compose logs -f go-service

logs-loadgen:
	docker-compose logs -f load-generator

clean:
	@echo "Cleaning up..."
	docker-compose down -v

restart: down up

test:
	@echo "Sending test order request..."
	curl -s -X POST http://localhost:8080/order -H 'Content-Type: application/json' -d '{"item":"widget","quantity":5}' | python3 -m json.tool

status:
	docker-compose ps

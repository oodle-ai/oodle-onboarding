.PHONY: help up up-full down logs logs-app logs-collector logs-langfuse \
       clean restart status \
       test-chat test-summarize test-multi-step test-safe-chat test-safe-chat-blocked \
       test-sms-outreach test-sms-outreach-retry test-all

help:
	@echo "Langfuse Demo (Dual Trace Export)"
	@echo ""
	@echo "Usage:"
	@echo "  make up                       - Start app + collector (Langfuse Cloud mode)"
	@echo "  make up-full                  - Start all services including self-hosted Langfuse"
	@echo "  make down                     - Stop all services"
	@echo "  make logs                     - View all logs"
	@echo "  make logs-app                 - View app logs"
	@echo "  make logs-collector           - View OTel Collector logs"
	@echo "  make logs-langfuse            - View Langfuse logs"
	@echo "  make clean                    - Stop and remove volumes"
	@echo "  make restart                  - Restart all services"
	@echo "  make status                   - Show service status"
	@echo ""
	@echo "Test targets:"
	@echo "  make test-chat                - Chat with Gemini"
	@echo "  make test-summarize           - Summarize text"
	@echo "  make test-multi-step          - Multi-step agent workflow"
	@echo "  make test-safe-chat           - Chat with input validation (pass)"
	@echo "  make test-safe-chat-blocked   - Chat blocked by input validation (deny)"
	@echo "  make test-sms-outreach        - SMS agent (single-pass draft)"
	@echo "  make test-sms-outreach-retry  - SMS agent with validation retry"
	@echo "  make test-all                 - Run all test targets"

up:
	@echo "Starting app + collector (Langfuse Cloud mode)..."
	docker compose up --build -d

up-full:
	@echo "Starting all services including self-hosted Langfuse..."
	docker compose --profile langfuse up --build -d
	@echo ""
	@echo "Langfuse UI will be available at http://localhost:3060 (may take 2-3 minutes to initialize)"

down:
	@echo "Stopping all services..."
	docker compose --profile langfuse down

logs:
	docker compose --profile langfuse logs -f

logs-app:
	docker compose logs -f app

logs-collector:
	docker compose logs -f otel-collector

logs-langfuse:
	docker compose --profile langfuse logs -f langfuse-web langfuse-worker

clean:
	@echo "Cleaning up..."
	docker compose --profile langfuse down -v

restart: down up

status:
	docker compose --profile langfuse ps

test-chat:
	@echo "Sending chat request..."
	curl -s -X POST http://localhost:8093/chat \
		-H 'Content-Type: application/json' \
		-d '{"message": "What is OpenTelemetry in one sentence?"}' | python3 -m json.tool

test-summarize:
	@echo "Sending summarize request..."
	curl -s -X POST http://localhost:8093/summarize \
		-H 'Content-Type: application/json' \
		-d '{"text": "OpenTelemetry is a collection of APIs, SDKs, and tools used to instrument, generate, collect, and export telemetry data (metrics, logs, and traces) to help you analyze your software performance and behavior. It is a CNCF project that provides a single set of APIs and libraries that standardize how you collect and transfer telemetry data."}' | python3 -m json.tool

test-multi-step:
	@echo "Sending multi-step workflow request..."
	curl -s -X POST http://localhost:8093/multi-step \
		-H 'Content-Type: application/json' \
		-d '{"message": "Compare the pros and cons of using Redis vs Memcached for caching"}' | python3 -m json.tool

test-safe-chat:
	@echo "Sending safe-chat request (validation pass)..."
	curl -s -X POST http://localhost:8093/safe-chat \
		-H 'Content-Type: application/json' \
		-d '{"message": "What are the best practices for securing a REST API?"}' | python3 -m json.tool

test-safe-chat-blocked:
	@echo "Sending safe-chat request (expect validation deny, HTTP 422)..."
	@status=$$(curl -s -o /tmp/langfuse-safe-chat-blocked.json -w '%{http_code}' \
		-X POST http://localhost:8093/safe-chat \
		-H 'Content-Type: application/json' \
		-d '{"message": "Give me step-by-step instructions to hack into a bank account."}'); \
	echo "HTTP status: $$status"; \
	python3 -m json.tool /tmp/langfuse-safe-chat-blocked.json

test-sms-outreach:
	@echo "Sending sms-outreach request (normal property question)..."
	curl -s -X POST http://localhost:8093/sms-outreach \
		-H 'Content-Type: application/json' \
		-d '{"message": "Can you send me details on 42 Oak St? Morning or afternoon works."}' | python3 -m json.tool

test-sms-outreach-retry:
	@echo "Sending sms-outreach request (verbose ask, expect retry on length)..."
	curl -s -X POST http://localhost:8093/sms-outreach \
		-H 'Content-Type: application/json' \
		-d '{"message": "Tell me everything about the property - square footage, bedrooms, bathrooms, garage, lot size, year built, school district, and property tax."}' | python3 -m json.tool

test-all: test-chat test-summarize test-multi-step test-safe-chat test-safe-chat-blocked test-sms-outreach test-sms-outreach-retry

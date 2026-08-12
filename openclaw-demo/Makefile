.PHONY: help up down logs logs-openclaw logs-collector clean restart status \
       ask heartbeat tools shell plugins test-all

MESSAGE ?= Reply with exactly HEARTBEAT_OK and nothing else.
SESSION ?= demo

help:
	@echo "OpenClaw Demo (real OpenClaw + real Langfuse SDK)"
	@echo ""
	@echo "Usage:"
	@echo "  make up               - Start OpenClaw + collector"
	@echo "  make down             - Stop all services"
	@echo "  make logs             - View all logs"
	@echo "  make logs-openclaw    - View OpenClaw logs"
	@echo "  make logs-collector   - View OTel Collector logs"
	@echo "  make clean            - Stop and remove volumes"
	@echo "  make restart          - Restart all services"
	@echo "  make status           - Show service status"
	@echo "  make plugins          - Show the loaded plugin list"
	@echo "  make shell            - Shell into the OpenClaw container"
	@echo ""
	@echo "Agent turns (each one produces a trace):"
	@echo "  make heartbeat        - A one-line turn, no tools"
	@echo "  make tools            - A turn that makes the agent use a tool"
	@echo "  make ask MESSAGE=...  - A turn with your own message"
	@echo "  make test-all         - Run both canned turns"
	@echo ""
	@echo "Variables: MESSAGE, SESSION (session key, groups turns into a session)"

up:
	@echo "Starting OpenClaw + collector..."
	docker compose up --build -d
	@echo ""
	@echo "Run a turn with: make heartbeat"

down:
	docker compose down

logs:
	docker compose logs -f

logs-openclaw:
	docker compose logs -f openclaw

logs-collector:
	docker compose logs -f otel-collector

clean:
	docker compose down -v

restart: down up

status:
	docker compose ps

plugins:
	docker compose exec openclaw openclaw plugins list

shell:
	docker compose exec openclaw sh

# Each turn is a one-shot embedded run: OpenClaw calls the model, the plugin
# records the Langfuse observations, and the spans are flushed before exit.
ask:
	docker compose exec openclaw \
		openclaw agent --local --session-key $(SESSION) -m "$(MESSAGE)"

heartbeat:
	@$(MAKE) ask MESSAGE="Reply with exactly HEARTBEAT_OK and nothing else."

tools:
	@$(MAKE) ask MESSAGE="Read the file /etc/hostname and tell me what is in it."

test-all: heartbeat tools

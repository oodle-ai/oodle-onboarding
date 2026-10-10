.PHONY: help up down logs clean replay replay-pii voice voice-logs verify-local status

# Every target sees the voice services, so down and clean stop them too.
COMPOSE := docker compose --profile voice

help: ## Show this help
	@echo "LiveKit Voice Agent Trace Demo"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; \
			{printf "  make %-13s - %s\n", $$1, $$2}'

up: ## Start the OTel Collector for the replay
	@echo "Starting OTel Collector..."
	docker compose up -d otel-collector

replay: ## Replay the sample trace via OTLP
	@echo "Replaying LiveKit sample trace..."
	static-replay/replay.py static-replay/sample-trace.json --fresh-ids

replay-pii: ## Replay it as an agent that marks personal data
	@echo "Replaying LiveKit sample trace, personal data marked..."
	static-replay/replay.py static-replay/sample-trace.json --fresh-ids --mark-pii

logs: ## View collector logs
	docker compose logs -f otel-collector

voice: ## Start LiveKit, the voice agent and its web page
	$(COMPOSE) up --build -d livekit agent web
	@echo "Open http://localhost:7870, pick a PII mode and start a call."

voice-logs: ## Tail the voice agent's logs
	$(COMPOSE) logs -f agent

verify-local: ## Offline check of both PII modes, no accounts needed
	$(COMPOSE) run --rm --no-deps -T web python verify_local.py

status: ## Show service status
	$(COMPOSE) ps

down: ## Stop everything
	$(COMPOSE) down

clean: ## Stop everything, remove volumes and the voice agent image
	$(COMPOSE) down -v --rmi local --remove-orphans

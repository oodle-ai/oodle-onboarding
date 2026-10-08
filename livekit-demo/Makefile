.PHONY: up down logs clean replay replay-pii status help

help:
	@echo "LiveKit Voice Agent Trace Demo"
	@echo ""
	@echo "Usage:"
	@echo "  make up       - Start OTel Collector"
	@echo "  make down     - Stop OTel Collector"
	@echo "  make logs     - View collector logs"
	@echo "  make replay   - Replay sample trace via OTLP"
	@echo "  make replay-pii - Replay it as an agent that marks personal data"
	@echo "  make clean    - Stop and remove volumes"
	@echo "  make status   - Show service status"

up:
	@echo "Starting OTel Collector..."
	docker compose up -d

down:
	@echo "Stopping OTel Collector..."
	docker compose down

logs:
	docker compose logs -f otel-collector

clean:
	@echo "Cleaning up..."
	docker compose down -v

replay:
	@echo "Replaying LiveKit sample trace..."
	./replay.py sample-trace.json --fresh-ids

replay-pii:
	@echo "Replaying LiveKit sample trace, personal data marked..."
	./replay.py sample-trace.json --fresh-ids --mark-pii

status:
	docker compose ps

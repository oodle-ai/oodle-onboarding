.PHONY: up down logs clean restart help

# Default agent
AGENT ?= fluent-bit

# Validate agent choice
VALID_AGENTS := fluent-bit vector otel
ifeq ($(filter $(AGENT),$(VALID_AGENTS)),)
    $(error Invalid AGENT. Choose from: fluent-bit, vector, otel)
endif

# Compose files
BASE_COMPOSE := -f docker-compose.base.yml
AGENT_COMPOSE := -f docker-compose.$(AGENT).yml
COMPOSE_FILES := $(BASE_COMPOSE) $(AGENT_COMPOSE)

help:
	@echo "OpenSearch Dual-Write Setup"
	@echo ""
	@echo "Available agents: fluent-bit, vector, otel"
	@echo ""
	@echo "Usage:"
	@echo "  make up AGENT=<agent>        - Start with specified agent (default: fluent-bit)"
	@echo "  make down                     - Stop all services"
	@echo "  make logs                     - View all logs"
	@echo "  make logs-app                 - View only app logs"
	@echo "  make logs-agent               - View only agent logs"
	@echo "  make clean                    - Stop and remove volumes"
	@echo "  make restart AGENT=<agent>    - Restart with specified agent"
	@echo ""
	@echo "Examples:"
	@echo "  make up                       - Start with Fluent Bit (default)"
	@echo "  make up AGENT=vector          - Start with Vector"
	@echo "  make up AGENT=otel            - Start with OpenTelemetry"

up:
	@echo "Starting with $(AGENT)..."
	docker-compose $(COMPOSE_FILES) up --build -d

down:
	@echo "Stopping all services..."
	docker-compose -f docker-compose.base.yml \
		-f docker-compose.fluent-bit.yml \
		-f docker-compose.vector.yml \
		-f docker-compose.otel.yml \
		down 2>/dev/null || true

logs:
	docker-compose $(COMPOSE_FILES) logs -f

logs-app:
	docker-compose $(COMPOSE_FILES) logs -f demo-app

logs-agent:
	@if [ "$(AGENT)" = "fluent-bit" ]; then \
		docker-compose $(COMPOSE_FILES) logs -f fluent-bit; \
	elif [ "$(AGENT)" = "vector" ]; then \
		docker-compose $(COMPOSE_FILES) logs -f vector; \
	elif [ "$(AGENT)" = "otel" ]; then \
		docker-compose $(COMPOSE_FILES) logs -f otel-collector; \
	fi

clean:
	@echo "Cleaning up..."
	docker-compose -f docker-compose.base.yml \
		-f docker-compose.fluent-bit.yml \
		-f docker-compose.vector.yml \
		-f docker-compose.otel.yml \
		down -v 2>/dev/null || true

restart: down up

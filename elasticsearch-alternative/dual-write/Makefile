.PHONY: up down logs clean restart help

# Default agent
AGENT ?= fluent-bit

# Validate agent choice
VALID_AGENTS := fluent-bit vector otel logstash
ifeq ($(filter $(AGENT),$(VALID_AGENTS)),)
    $(error Invalid AGENT. Choose from: fluent-bit, vector, otel, logstash)
endif

# Compose files
BASE_COMPOSE := -f docker-compose.base.yml
AGENT_COMPOSE := -f docker-compose.$(AGENT).yml
PROMETHEUS_COMPOSE := -f docker-compose.prometheus.yml
COMPOSE_FILES := $(BASE_COMPOSE) $(AGENT_COMPOSE) $(PROMETHEUS_COMPOSE)

# All compose files (for down/clean across all agents)
ALL_COMPOSE := -f docker-compose.base.yml \
	-f docker-compose.fluent-bit.yml \
	-f docker-compose.vector.yml \
	-f docker-compose.otel.yml \
	-f docker-compose.logstash.yml \
	-f docker-compose.prometheus.yml

help:
	@echo "Elasticsearch Dual-Write Setup"
	@echo ""
	@echo "Available agents: fluent-bit, vector, otel, logstash"
	@echo ""
	@echo "Usage:"
	@echo "  make up AGENT=<agent>        - Start with specified agent (default: fluent-bit)"
	@echo "  make down                     - Stop all services"
	@echo "  make logs                     - View all logs"
	@echo "  make logs-app                 - View only app logs"
	@echo "  make logs-agent               - View only agent logs"
	@echo "  make logs-prometheus           - View Prometheus logs"
	@echo "  make clean                    - Stop and remove volumes"
	@echo "  make restart AGENT=<agent>    - Restart with specified agent"
	@echo ""
	@echo "Examples:"
	@echo "  make up                       - Start with Fluent Bit (default)"
	@echo "  make up AGENT=vector          - Start with Vector"
	@echo "  make up AGENT=otel            - Start with OpenTelemetry"
	@echo "  make up AGENT=logstash        - Start with Filebeat + Logstash"

up:
	@echo "Starting with $(AGENT)..."
	AGENT=$(AGENT) docker-compose $(COMPOSE_FILES) up --build -d

down:
	@echo "Stopping all services..."
	docker-compose $(ALL_COMPOSE) down 2>/dev/null || true

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
	elif [ "$(AGENT)" = "logstash" ]; then \
		docker-compose $(COMPOSE_FILES) logs -f logstash filebeat; \
	fi

logs-prometheus:
	docker-compose $(COMPOSE_FILES) logs -f prometheus

clean:
	@echo "Cleaning up..."
	docker-compose $(ALL_COMPOSE) down -v 2>/dev/null || true

restart: down up

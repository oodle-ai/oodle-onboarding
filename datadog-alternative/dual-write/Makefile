.PHONY: up down logs clean restart help

# Default configuration method
METHOD ?= env

# Validate method choice
VALID_METHODS := env yaml-config
ifeq ($(filter $(METHOD),$(VALID_METHODS)),)
    $(error Invalid METHOD. Choose from: env, yaml-config)
endif

# Compose files
BASE_COMPOSE := -f docker-compose.base.yml
METHOD_COMPOSE := -f docker-compose.$(METHOD).yml
COMPOSE_FILES := $(BASE_COMPOSE) $(METHOD_COMPOSE)

help:
	@echo "Datadog Dual-Write Setup"
	@echo ""
	@echo "Available methods: env, yaml-config"
	@echo ""
	@echo "Usage:"
	@echo "  make up METHOD=<method>      - Start with specified method (default: env)"
	@echo "  make down                    - Stop all services"
	@echo "  make logs                    - View all logs"
	@echo "  make logs-app                - View only app logs"
	@echo "  make logs-agent              - View only Datadog Agent logs"
	@echo "  make clean                   - Stop and remove volumes"
	@echo "  make restart METHOD=<method> - Restart with specified method"
	@echo ""
	@echo "Examples:"
	@echo "  make up                      - Start with env var method (default)"
	@echo "  make up METHOD=yaml-config   - Start with YAML config method"

up:
	@echo "Starting with $(METHOD) method..."
	docker-compose $(COMPOSE_FILES) up --build -d

down:
	@echo "Stopping all services..."
	docker-compose -f docker-compose.base.yml \
		-f docker-compose.env.yml \
		-f docker-compose.yaml-config.yml \
		down 2>/dev/null || true

logs:
	docker-compose $(COMPOSE_FILES) logs -f

logs-app:
	docker-compose $(COMPOSE_FILES) logs -f demo-app

logs-agent:
	docker-compose $(COMPOSE_FILES) logs -f datadog-agent

clean:
	@echo "Cleaning up..."
	docker-compose -f docker-compose.base.yml \
		-f docker-compose.env.yml \
		-f docker-compose.yaml-config.yml \
		down -v 2>/dev/null || true

restart: down up

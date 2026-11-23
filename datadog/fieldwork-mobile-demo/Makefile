.PHONY: help install dev api mobile up up-observability up-oodle up-oodle-only down clean logs check export doctor
help:
	@echo "install: install dependencies | dev: API + browser preview | mobile: native Metro server"
	@echo "up: API + PostgreSQL + Redis + worker | up-observability: add Datadog Agent"
	@echo "up-oodle: Agent sends traces to Datadog and Oodle | up-oodle-only: Agent sends to Oodle only"
	@echo "down: stop services | clean: remove demo database | logs: follow service logs"
	@echo "check: types + behavior tests | export: bundle all platforms | doctor: Expo dependency checks"
install:
	npm ci
dev:
	npm run dev
api:
	npm run api
mobile:
	npm start -- --lan
up:
	docker compose up --build -d
up-observability:
	docker compose --profile observability up --build -d
up-oodle:
	docker compose -f compose.yaml -f compose.oodle.yaml --profile observability up --build -d
up-oodle-only:
	docker compose -f compose.yaml -f compose.oodle-only.yaml --profile observability up --build -d
down:
	docker compose --profile observability down
clean:
	docker compose --profile observability down --volumes
logs:
	docker compose logs -f api worker
check:
	npm run check
export:
	npm run export:web
	npm run export:native
doctor:
	npx expo-doctor

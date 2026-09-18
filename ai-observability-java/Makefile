.PHONY: up down logs build restart chat

up:
	docker compose up --build -d

build:
	docker compose build

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f

chat:
	curl -s -X POST "http://localhost:8094/chat?q=What%20is%20the%20weather%20in%20Paris"

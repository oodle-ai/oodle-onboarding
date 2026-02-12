.PHONY: up down logs clean restart

up:
	docker-compose up --build -d

down:
	docker-compose down

logs:
	docker-compose logs -f

logs-app:
	docker-compose logs -f demo-app

clean:
	docker-compose down -v

restart: down up

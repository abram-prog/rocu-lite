
.PHONY: up down logs build fmt lint

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=150

build:
	docker compose build

fmt:
	@echo "No formatters configured yet."

lint:
	@echo "No linters configured yet."

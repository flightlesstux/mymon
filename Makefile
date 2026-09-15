.PHONY: up down logs ps restart-collector test lint psql build

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build collector

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

restart-collector:
	docker compose up -d --build --force-recreate collector

test:
	cd collector && python -m pytest -q

lint:
	cd collector && ruff check .

psql:
	docker compose exec postgres psql -U $${POSTGRES_USER:-mymon} -d $${POSTGRES_DB:-mymon}

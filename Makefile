.PHONY: help up down restart build rebuild logs logs-collector ps \
        venv lint test dashboards verify ci \
        restart-collector psql prom-reload clean

help:
	@echo "make up                start the full stack (build if needed)"
	@echo "make down              stop the stack"
	@echo "make restart           recreate every container"
	@echo "make build             rebuild the collector image"
	@echo "make rebuild           rebuild collector and restart it in place"
	@echo "make logs              follow all container logs"
	@echo "make logs-collector    follow collector logs only"
	@echo "make ps                container status"
	@echo "make venv              create collector/.venv with dev dependencies"
	@echo "make lint              ruff check the collector"
	@echo "make test              run the collector test suite"
	@echo "make dashboards        regenerate grafana/dashboards/*.json from grafana/dashgen/"
	@echo "make verify            check health, anonymous access, read-only role, prometheus"
	@echo "make ci                lint + test + dashboards + verify (what a PR should pass)"
	@echo "make psql              open a psql shell as the writer role"
	@echo "make prom-reload       hot-reload prometheus.yml without restarting the container"
	@echo "make clean             stop the stack and remove all data volumes (DESTRUCTIVE)"

# --- stack lifecycle ------------------------------------------------------

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose up -d --build --force-recreate

build:
	docker compose build collector

rebuild: build
	docker compose up -d --force-recreate collector

logs:
	docker compose logs -f --tail=200

logs-collector:
	docker compose logs -f --tail=200 collector

ps:
	docker compose ps

restart-collector: rebuild

clean:
	docker compose down -v

# --- collector development -------------------------------------------------

venv:
	cd collector && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'

lint:
	cd collector && . .venv/bin/activate && ruff check .

test:
	cd collector && . .venv/bin/activate && python -m pytest -q

# --- dashboards --------------------------------------------------------

dashboards:
	python3 grafana/dashgen/generate_all.py

# --- verification / ci --------------------------------------------------

verify:
	bash scripts/verify.sh

ci: lint test dashboards verify

# --- misc ----------------------------------------------------------------

psql:
	docker compose exec postgres psql -U $${POSTGRES_USER:-mymon} -d $${POSTGRES_DB:-mymon}

prom-reload:
	docker compose kill -s SIGHUP prometheus

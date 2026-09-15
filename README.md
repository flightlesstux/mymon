# mymon

Public, read-only Grafana dashboards fed by free public data: weather for 21 world cities,
central-bank reserve assets, FX and crypto, earthquakes, the ISS, Bitcoin network stats,
space weather, CO₂, fuel and commodity prices, consumer-price indices.

Live: http://ermis.tplinkdns.com:3000

## How it works

```
internet ──► :3000 grafana ──(read-only role)──► postgres ◄──(writer role)── collector ──► public APIs
```

| Service              | Image                                  | Role                                                            |
|----------------------|-----------------------------------------|-----------------------------------------------------------------|
| `grafana`            | `grafana/grafana-oss`                   | UI. Only published port. Datasources + dashboards provisioned from files. |
| `postgres`           | `postgres:17-alpine`                    | Business data. Not published. Schema and roles created on first start. |
| `collector`          | built from `./collector`                | Python scheduler polling each source on its own interval, upserting rows. Exposes `/metrics` internally. |
| `prometheus`         | `prom/prometheus`                       | Operational metric history (90 days). Not published. Scrapes `collector`, `postgres-exporter`, `grafana`. |
| `postgres-exporter`  | `prometheuscommunity/postgres-exporter` | Exposes Postgres stats (`pg_up`, connections, database size) to Prometheus. |

Anonymous visitors get the Grafana *Viewer* role. Grafana connects to Postgres with a
role that can only `SELECT`, so nothing a viewer does can change data. Dashboards are
provisioned from JSON files, so they cannot be edited from the UI either; change the
generator script and regenerate (see below).

Business data (weather, reserves, FX, ...) lives in Postgres, queried straight from the
dashboards — that already gives full history for every value. Prometheus is separate:
it only tracks *the collector's own health* (is each source running, how long does a run
take, is it failing) and basic Postgres server stats, so operational history survives a
restart and isn't limited to the single "last run" row `collector_run` keeps per source.
See the **Collector Health** dashboard.

## Run

Every repeated action goes through the Makefile — see `make help` for the full list.

```bash
cp .env.example .env      # set the passwords
make up                   # build and start every service
make logs                 # follow all containers
make verify               # health, anonymous access, read-only role, prometheus targets
```

Grafana is on http://localhost:3000. Admin credentials come from `.env`.

`make ci` runs lint, tests, dashboard generation and verification together — what a
change should pass before it's pushed.

## Data sources

Phase 1 needs no API keys. Phase 2 modules activate automatically when their key is set
in `.env` (see `.env.example`).

| Source module        | Upstream                                  | Interval |
|----------------------|-------------------------------------------|----------|
| `weather`            | Open-Meteo forecast, air quality, archive | 15 min   |
| `reserves_worldbank` | World Bank indicators                     | daily    |
| `reserves_ecb`       | ECB Data Portal                           | daily    |
| `reserves_tcmb`      | TCMB EVDS (key)                           | daily    |
| `fx`                 | Frankfurter (ECB), TCMB                   | hourly   |
| `crypto`             | Binance public API                        | 1 min    |
| `earthquakes_usgs`   | USGS GeoJSON feeds                        | 5 min    |
| `earthquakes_afad`   | AFAD (Turkey)                             | 10 min   |
| `iss`                | wheretheiss.at                            | 1 min    |
| `btc_network`        | mempool.space                             | 2 min    |
| `space_weather`      | NOAA SWPC                                 | 10 min   |
| `co2`                | NOAA GML Mauna Loa                        | daily    |
| `fuel_eu`            | EC Weekly Oil Bulletin                    | daily    |
| `fuel_tr`            | Turkish pump prices                       | 6 h      |
| `commodities_wb`     | World Bank Pink Sheet                     | daily    |
| `commodities_stooq`  | Stooq daily CSV                           | hourly   |
| `price_indices`      | World Bank, The Economist, FAO            | daily    |
| `energy_prices_eu`   | Eurostat                                  | daily    |
| `fred`               | FRED (key)                                | daily    |
| `eia`                | EIA (key)                                 | daily    |
| `opensky`            | OpenSky Network (key)                     | 5 min    |
| `bis_policy_rates`   | BIS                                       | daily    |

Enable, disable or re-time any module in `collector/config/sources.yml`. Cities live in
`collector/config/cities.yml` (keep in sync with the `city` seed in `postgres/init/001_schema.sql`).

## Adding a source

Create `collector/mymon_collector/sources/<name>.py` exposing:

```python
from mymon_collector.source import Ctx, Rows, Source

def fetch(ctx: Ctx) -> Rows:
    data = ctx.http.get("https://example.org/api").json()
    return [("some_table", [{"ts": ..., "key": ..., "value": ...}])]

SOURCE = Source(name="<name>", interval=600, fetch=fetch, tables=["some_table"])
```

Rows are upserted on the table's primary key, so returning overlapping data is fine.
An optional `backfill(ctx)` runs once when a listed table is empty. Add a fixture-based
test under `collector/tests/sources/` and run `make test`. Every run — success or
failure — updates the Prometheus metrics in `mymon_collector/metrics.py` automatically;
nothing extra to do there.

## Dashboards

Dashboards are code, not JSON edited by hand. Each file in `grafana/dashgen/` builds one
dashboard with the helpers in `grafana/dashgen/_lib.py` (panel layout, the shared color
palette, Postgres and Prometheus query builders) and writes it to `grafana/dashboards/`.

```bash
make dashboards   # regenerate every dashboard from grafana/dashgen/*.py
```

Add a new dashboard by adding a new script next to the others; `generate_all.py` picks it
up automatically. Commit the generated JSON alongside the script that produced it.

## Metrics and history

- **Business data** (weather, FX, reserves, ...): stored in Postgres by the collector,
  queried directly by the dashboards. This is the primary, long-retention history.
- **Operational metrics** (is a source healthy, how long did it take, Postgres
  connections/size): scraped by Prometheus every 30 seconds and kept for 90 days
  (`prometheus/prometheus.yml`, `--storage.tsdb.retention.time`). Visible on the
  **Collector Health** dashboard via the `MymonPrometheus` datasource.

Both datasources are provisioned automatically; there's nothing to wire up in the
Grafana UI.

## Development

```bash
make venv    # create collector/.venv with dev dependencies
make lint    # ruff check
make test    # pytest
```

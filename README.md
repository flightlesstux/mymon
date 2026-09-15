# mymon

Public, read-only Grafana dashboards fed by free public data: weather for 21 world cities,
central-bank reserve assets, FX and crypto, earthquakes, the ISS, Bitcoin network stats,
space weather, CO₂, fuel and commodity prices, consumer-price indices.

Live: http://ermis.tplinkdns.com:3000

## How it works

```
internet ──► :3000 grafana ──(read-only role)──► postgres ◄──(writer role)── collector ──► public APIs
```

| Service     | Image                        | Role                                                            |
|-------------|------------------------------|-----------------------------------------------------------------|
| `grafana`   | `grafana/grafana-oss`        | UI. Only published port. Datasource + dashboards provisioned from files. |
| `postgres`  | `postgres:17-alpine`         | Storage. Not published. Schema and roles created on first start. |
| `collector` | built from `./collector`     | Python scheduler polling each source on its own interval, upserting rows. |

Anonymous visitors get the Grafana *Viewer* role. Grafana connects to Postgres with a
role that can only `SELECT`, so nothing a viewer does can change data. Dashboards are
provisioned from JSON files, so they cannot be edited from the UI either; change the
JSON and the provider reloads it within 30 seconds.

## Run

```bash
cp .env.example .env      # set the passwords
make up                   # docker compose up -d --build
make logs                 # follow all containers
```

Grafana is on http://localhost:3000. Admin credentials come from `.env`.

Useful targets: `make ps`, `make restart-collector`, `make psql`, `make test`, `make lint`.

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
test under `collector/tests/sources/` and run `make test`.

## Development

```bash
cd collector
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
ruff check . && pytest -q
```

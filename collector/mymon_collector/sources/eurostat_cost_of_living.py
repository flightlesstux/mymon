"""Germany, Italy, Spain, Greece, Turkey and France: CPI broken into all 12 top-level
COICOP spending categories via Eurostat (``prc_hicp_midx``) — the same dataset
eurostat_metrics.py and eurostat_grocery.py already use, one level up from grocery's 61
leaf products. Mirrors NL's nl_cost_of_living.py category breakdown.

Shares the JSON-stat decoder and country-code mapping with eurostat_metrics.py.
"""

from __future__ import annotations

import logging
from typing import Any

from ..source import Ctx, Rows, Source
from .eurostat_metrics import GEO_TO_ISO3, GEOS, _decode, _period_from_time_code

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
SINCE = "2000-01"

# COICOP division code -> our indicator slug. Confirmed live against the coicop
# dimension list (2026-09).
CATEGORIES: dict[str, str] = {
    "CP01": "food_and_drink",
    "CP02": "alcohol_and_tobacco",
    "CP03": "clothing_and_footwear",
    "CP04": "housing_water_energy",
    "CP05": "furnishings_household",
    "CP06": "health",
    "CP07": "transport",
    "CP08": "communication",
    "CP09": "recreation_and_culture",
    "CP10": "education",
    "CP11": "restaurants_and_hotels",
    "CP12": "misc_goods_and_services",
}


def _row(period, country_iso3: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _category_rows(ctx: Ctx, coicop: str, slug: str) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, "coicop": coicop, "unit": "I15",
              "sinceTimePeriod": SINCE}
    resp = ctx.http.get(f"{BASE}/prc_hicp_midx", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"cpi_cat_{slug}", value, "2015=100"))
    return rows


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, str], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for coicop, slug in upstreams:
        try:
            part = _category_rows(ctx, coicop, slug)
        except Exception as exc:  # noqa: BLE001 - one category must not sink the others
            log.warning("eurostat_cost_of_living: %s failed: %s", slug, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_cost_of_living: %s returned no rows", slug)
            failures += 1
            continue
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, tuple(CATEGORIES.items()))
    if not rows:
        raise RuntimeError("eurostat_cost_of_living: every upstream failed")
    log.info("eurostat_cost_of_living: %d rows (%d/%d upstream failures)",
              len(rows), failures, len(CATEGORIES))
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_cost_of_living",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: CPI broken into all 12 "
        "top-level COICOP spending categories (housing, transport, health, "
        "education, etc.), monthly since 2000 where the data goes back that far."
    ),
)

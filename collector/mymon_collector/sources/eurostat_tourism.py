"""Germany, Italy, Spain, Greece, Turkey and France: nights spent at tourist
accommodation via Eurostat (``tour_occ_nim``), all six countries in one call. Monthly,
since 2000 where each country's series goes back that far (confirmed live — Turkey and
France both start later than the others).

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


def _row(period, country_iso3: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _nights_spent_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {
        "format": "JSON", "lang": "en", "geo": GEOS,
        "unit": "NR", "c_resid": "TOTAL", "nace_r2": "I551-I553",
        "sinceTimePeriod": "2000-01",
    }
    resp = ctx.http.get(f"{BASE}/tour_occ_nim", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "tourism_nights_spent", value, "count"))
    return rows


def fetch(ctx: Ctx) -> Rows:
    rows = _nights_spent_rows(ctx)
    if not rows:
        raise RuntimeError("eurostat_tourism: no rows returned")
    log.info("eurostat_tourism: %d rows", len(rows))
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_tourism",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: nights spent at tourist "
        "accommodation (hotels and similar), monthly, since 2000 where the data goes "
        "back that far."
    ),
)

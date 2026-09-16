"""Germany, Italy, Spain, Greece, Turkey and France: construction sector production
index via Eurostat (``sts_copr_m``), all six countries in one call.

Greece has no published data at all for this specific indicator/sector combination
(confirmed live: an EL-only, otherwise unfiltered query returns zero values) — a real
gap in Eurostat's coverage, not a query bug; that stat/panel shows "No data" honestly.

Two other construction series were checked live and dropped, not silently skipped:
producer/cost prices (``sts_copi_m``) has zero published data for Germany in this
dataset (the ``geo`` dimension itself comes back empty for a Germany-only query,
independent of any other filter — a real gap in what Eurostat publishes, not a query
bug), and building permits (``sts_cobp_m``/``sts_cobp_a``) returns zero values for
every combination of unit/geo tried, for every country. Both would need chasing per
national statistics office to fill in, which defeats the point of the shared-Eurostat
approach this module exists for.

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


def _construction_production_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {
        "format": "JSON", "lang": "en", "geo": GEOS,
        "indic_bt": "PRD", "nace_r2": "F", "s_adj": "SCA", "unit": "I21",
        "sinceTimePeriod": "2000-01",
    }
    resp = ctx.http.get(f"{BASE}/sts_copr_m", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "construction_production_index", value, "2021=100"))
    return rows


def fetch(ctx: Ctx) -> Rows:
    rows = _construction_production_rows(ctx)
    if not rows:
        raise RuntimeError("eurostat_construction: no rows returned")
    log.info("eurostat_construction: %d rows", len(rows))
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_construction",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: construction sector "
        "production index, monthly, seasonally adjusted, since 2000 where the data "
        "goes back that far."
    ),
)

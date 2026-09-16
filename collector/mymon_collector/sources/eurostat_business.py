"""Germany and France only: business bankruptcy index by sector via Eurostat
(``sts_rb_m``). Confirmed live: Italy, Spain, Greece and Turkey return zero values for
this indicator under every unit/seasonal-adjustment combination tried — not a query
bug, those four countries simply aren't populated in this dataset. Rather than skip the
whole indicator because 4 of 6 countries lack it, DE and FR get real coverage.

Sectors are Eurostat's own top-level NACE groupings, not a 1:1 match to the more
granular SBI-code sectors NL's nl_construction.py uses.
"""

from __future__ import annotations

import logging
from typing import Any

from ..source import Ctx, Rows, Source
from .eurostat_metrics import _decode, _period_from_time_code

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

GEO_TO_ISO3: dict[str, str] = {"DE": "DEU", "FR": "FRA"}

# NACE Rev. 2 top-level grouping code -> our indicator slug. Confirmed live.
SECTORS: dict[str, str] = {
    "B-S_X_O_S94": "total",
    "B-E": "industry",
    "F": "construction",
    "G": "trade",
    "H": "transport",
    "I": "hospitality",
    "J": "ict",
    "K-N": "finance_real_estate_professional",
    "P-S_X_S94": "other_services",
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


def _bankruptcy_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": list(GEO_TO_ISO3), "indic_bt": "BKRT",
              "s_adj": "NSA", "unit": "I21", "sinceTimePeriod": "2015-01"}
    resp = ctx.http.get(f"{BASE}/sts_rb_m", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        slug = SECTORS.get(dims.get("nace_r2", ""))
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if slug is None or iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"bankruptcy_index_{slug}", value, "2021=100"))
    return rows


def fetch(ctx: Ctx) -> Rows:
    rows = _bankruptcy_rows(ctx)
    if not rows:
        raise RuntimeError("eurostat_business: no rows returned")
    log.info("eurostat_business: %d rows", len(rows))
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_business",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, France only: business bankruptcy index by sector (Eurostat "
        "sts_rb_m), monthly since 2015 — Italy/Spain/Greece/Turkey have no data at "
        "all for this indicator."
    ),
)

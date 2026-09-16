"""Germany, Italy, Spain, Greece, Turkey and France: national port cargo tonnage via
Eurostat (``mar_mg_aa_cwh``), all six countries in one call. Annual, since 1997.

This dataset uses ``rep_mar`` (reporting country) as its geo-equivalent dimension, not
``geo`` like every other dataset in this project — confirmed live (a ``geo=`` filter on
this dataset 400s with "Dimension GEO is not defined").

Country-level totals only, not per-port like NL's nl_ports.py (Rotterdam/Amsterdam/etc.)
— Eurostat's per-port breakdown (``mar_mg_am_cwhc``) exists but wasn't pulled in for
this pass; the country-level total is the useful headline number here.

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


def _port_cargo_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "rep_mar": GEOS, "unit": "THS_T",
              "sinceTimePeriod": "2000"}
    resp = ctx.http.get(f"{BASE}/mar_mg_aa_cwh", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("rep_mar", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "port_cargo_1000t", value, "1000 tonnes"))
    return rows


def fetch(ctx: Ctx) -> Rows:
    rows = _port_cargo_rows(ctx)
    if not rows:
        raise RuntimeError("eurostat_ports: no rows returned")
    log.info("eurostat_ports: %d rows", len(rows))
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_ports",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: total national port cargo "
        "tonnage, annual, since 2000 where the data goes back that far."
    ),
)

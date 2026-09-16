"""NUTS2-region-level breakdown for the same six countries as eurostat_metrics.py —
unemployment, GDP per capita, and population, one row per region instead of per country.

Eurostat's ``geo`` dimension has no prefix/wildcard filter, so there's no way to ask for
"just the NUTS2 regions of these six countries" server-side. Instead each indicator is
fetched with geo unfiltered (one HTTP call, whole EU + candidate countries, confirmed
live at ~200-300KB/call — small enough for a daily pull) and filtered client-side to
codes that both start with one of our six country prefixes and are exactly
``len(prefix) + 2`` characters, which is how NUTS2 codes are formed under this scheme for
all six (e.g. ``DE21``, ``ITC1``, ``TR10`` — confirmed live, not a general NUTS rule).

Regions land in the same ``price_index`` table keyed by the *national* ``country_iso3``
(so they group onto each country's own dashboards) with the region code folded into the
indicator name (``regional_unemployment_pct_DE21``) — the same pattern already used for
grocery products, COICOP categories and bankruptcy sectors. Human-readable region names
are a plain-literal dict on the dashgen side (``_eurostat_common.REGION_LABELS``), not
looked up from the API at render time.
"""

from __future__ import annotations

import logging
from typing import Any

from ..source import Ctx, Rows, Source
from .eurostat_metrics import GEO_TO_ISO3, _decode, _period_from_time_code

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

PREFIXES = list(GEO_TO_ISO3)


def _region_iso3(geo: str) -> str | None:
    for prefix in PREFIXES:
        if geo.startswith(prefix) and len(geo) == len(prefix) + 2:
            return GEO_TO_ISO3[prefix]
    return None


def _row(period, country_iso3: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _regional_rows(
    ctx: Ctx, dataset: str, params: dict[str, Any], indicator_prefix: str, unit: str
) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", **params}
    resp = ctx.http.get(f"{BASE}/{dataset}", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        geo = dims.get("geo", "")
        iso3 = _region_iso3(geo)
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"{indicator_prefix}_{geo}", value, unit))
    return rows


def _unemployment_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _regional_rows(
        ctx, "lfst_r_lfu3rt", {"sex": "T", "age": "Y15-74", "unit": "PC", "isced11": "TOTAL"},
        "regional_unemployment_pct", "%")


def _gdp_per_capita_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _regional_rows(
        ctx, "nama_10r_2gdp", {"unit": "EUR_HAB"}, "regional_gdp_per_capita_eur", "EUR")


def _population_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _regional_rows(
        ctx, "demo_r_pjangrp3", {"sex": "T", "age": "TOTAL"}, "regional_population", "count")


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("eurostat_regional: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_regional: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_regional: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("unemployment", _unemployment_rows),
        ("gdp_per_capita", _gdp_per_capita_rows),
        ("population", _population_rows),
    ))
    if not rows:
        raise RuntimeError("eurostat_regional: every upstream failed")
    log.info("eurostat_regional: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_regional",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "NUTS2 regional breakdown (144 regions across Germany, Italy, Spain, Greece, "
        "Turkey and France) of unemployment rate, GDP per capita and population, via "
        "Eurostat."
    ),
)

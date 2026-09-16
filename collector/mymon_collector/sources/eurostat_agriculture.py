"""Germany, Italy, Spain, Greece and France: livestock and farm holdings via Eurostat's
farm structure survey (``ef_lsk_main``). Not Turkey — this dataset is EU-only, confirmed
live (Turkey simply doesn't appear in the ``geo`` dimension for this one).

Farm structure surveys run roughly every 3 years (2005, 2007, 2010, 2013, 2016, 2020,
2023), so this is much sparser than NL's annual CBS agriculture series — a real
characteristic of the upstream data, not a gap in this collector.

Shares the JSON-stat decoder and country-code mapping with eurostat_metrics.py rather
than duplicating it.
"""

from __future__ import annotations

import logging
from typing import Any

from ..source import Ctx, Rows, Source
from .eurostat_metrics import GEO_TO_ISO3, _decode, _period_from_time_code

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
GEOS = [g for g in GEO_TO_ISO3 if g != "TR"]  # ef_lsk_main has no Turkey data

FIXED = {"statinfo": "TOTAL", "farmtype": "TOTAL", "so_eur": "TOTAL", "uaarea": "TOTAL",
         "lsu": "TOTAL"}

ANIMALS: dict[str, str] = {
    "A2000": "cattle_count", "A3100": "pig_count", "A4100": "sheep_count",
    "A4200": "goat_count", "A5000": "poultry_count",
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


def _eurostat_get(ctx: Ctx, dataset: str, params: dict[str, Any]) -> list[tuple[dict, float]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, **FIXED, **params}
    resp = ctx.http.get(f"{BASE}/{dataset}", params=query)
    resp.raise_for_status()
    return _decode(resp.json())


def _livestock_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dims, value in _eurostat_get(ctx, "ef_lsk_main", {"unit": "HD"}):
        animal = ANIMALS.get(dims.get("animals", ""))
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if animal is None or iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, animal, value, "count"))
    return rows


def _holdings_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    params = {"unit": "HLD", "animals": "A0010X1000"}
    for dims, value in _eurostat_get(ctx, "ef_lsk_main", params):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "farm_holdings_with_livestock", value, "count"))
    return rows


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("eurostat_agriculture: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_agriculture: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_agriculture: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        seen[(r["period_date"], r["country_iso3"], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("livestock", _livestock_rows),
        ("holdings", _holdings_rows),
    ))
    if not rows:
        raise RuntimeError("eurostat_agriculture: every upstream failed")
    log.info("eurostat_agriculture: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, _dedupe(rows))]


SOURCE = Source(
    name="eurostat_agriculture",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, France: livestock (cattle/pigs/sheep/goats/"
        "poultry) and farm holdings count, via Eurostat's farm structure survey "
        "(every ~3 years, 2005-2023). Not Turkey — no data in this dataset."
    ),
)

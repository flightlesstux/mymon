"""Crime and road safety for Germany, Italy, Spain, Greece, Turkey, France and the
Netherlands. Nothing safety-related existed for any of these seven before this module.

Crime rates use Eurostat's harmonized ICCS offence classification, per 100,000
inhabitants for cross-country comparability (raw counts would just track population
size). Road deaths use per-million-inhabitants for the same reason. Both datasets have
small per-country/category gaps confirmed live (not every offence category is reported
by every country every year) — rows simply don't exist for those combinations rather
than being backfilled with a guess.

NL is included here (see eurostat_finance.py for the same reasoning) with its own local
GEO_TO_ISO3 and HTTP calls, not the shared six-country ``_eurostat_get``.
"""

from __future__ import annotations

import logging
from typing import Any

from ..source import Ctx, Rows, Source
from .eurostat_metrics import GEO_TO_ISO3 as _SIX_COUNTRY_GEO_TO_ISO3
from .eurostat_metrics import _decode, _period_from_time_code

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

GEO_TO_ISO3: dict[str, str] = {**_SIX_COUNTRY_GEO_TO_ISO3, "NL": "NLD"}
GEOS = list(GEO_TO_ISO3)


def _eurostat_get(ctx: Ctx, dataset: str, params: dict[str, Any]):
    query = {"format": "JSON", "lang": "en", "geo": GEOS, **params}
    resp = ctx.http.get(f"{BASE}/{dataset}", params=query)
    resp.raise_for_status()
    return _decode(resp.json())

CRIME_CATEGORIES: dict[str, str] = {
    "ICCS0101": "homicide", "ICCS0401": "robbery", "ICCS0501": "burglary",
    "ICCS0502": "theft", "ICCS0601": "drug_offences", "ICCS0701": "fraud",
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


def _crime_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    query = {"iccs": list(CRIME_CATEGORIES), "unit": "P_HTHAB"}
    for dims, value in _eurostat_get(ctx, "crim_off_cat", query):
        slug = CRIME_CATEGORIES.get(dims.get("iccs", ""))
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if slug is None or iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"crime_rate_per_100k_{slug}", value, "per 100k"))
    return rows


def _road_deaths_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    query = {"victim": "KIL", "unit": "P_MHAB"}
    for dims, value in _eurostat_get(ctx, "tran_r_acci", query):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "road_deaths_per_million", value, "per million"))
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
            log.warning("eurostat_safety: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_safety: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_safety: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("crime", _crime_rows),
        ("road_deaths", _road_deaths_rows),
    ))
    if not rows:
        raise RuntimeError("eurostat_safety: every upstream failed")
    log.info("eurostat_safety: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_safety",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France and the Netherlands via "
        "Eurostat: recorded crime rate by offence category (per 100,000 inhabitants) "
        "and road deaths (per million inhabitants)."
    ),
)

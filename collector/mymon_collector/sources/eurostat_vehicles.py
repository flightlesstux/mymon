"""Germany, Italy, Spain, Greece, Turkey and France: passenger car fleet by fuel type
via Eurostat (``road_eqs_carpda``), all six countries in one call per fuel type. Annual
stock counts (not new registrations — same limitation as NL's nl_vehicles.py: Eurostat
doesn't publish a fuel-type breakdown of new sales either), coverage starts around the
early 2010s for most countries, not full 2000+ depth.

Coverage is genuinely uneven per country/fuel (confirmed live): Greece has no petrol or
diesel rows in this dataset at all, only electric and a couple of LPG/gas points — shown
as "No data" honestly rather than backfilled with a guess.

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

FUEL_CODES: dict[str, str] = {
    "PET": "petrol", "DIE": "diesel", "ELC": "electric", "LPG": "lpg", "GAS": "cng",
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


def _fleet_rows_for_fuel(ctx: Ctx, fuel_code: str, fuel_slug: str) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, "unit": "NR",
              "mot_nrg": fuel_code, "sinceTimePeriod": "2000"}
    resp = ctx.http.get(f"{BASE}/road_eqs_carpda", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"vehicle_fleet_{fuel_slug}", value, "count"))
    return rows


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, str, str], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for fuel_code, fuel_slug, name in upstreams:
        try:
            part = _fleet_rows_for_fuel(ctx, fuel_code, fuel_slug)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("eurostat_vehicles: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_vehicles: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_vehicles: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    upstreams = tuple((code, slug, slug) for code, slug in FUEL_CODES.items())
    rows, failures = _run_upstreams(ctx, upstreams)
    if not rows:
        raise RuntimeError("eurostat_vehicles: every upstream failed")
    log.info("eurostat_vehicles: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_vehicles",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: passenger car fleet stock by "
        "fuel type (petrol/diesel/electric/LPG/CNG), annual, coverage starts around "
        "the early 2010s and varies by country and fuel type."
    ),
)

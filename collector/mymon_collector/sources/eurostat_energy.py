"""Germany, Italy, Spain, Greece, Turkey and France: consumer energy tariffs and
electricity production mix via Eurostat, all six countries in one call per indicator.

Gas and electricity household prices (``nrg_pc_202``/``nrg_pc_204``) use a mid-size
consumption band (households, 20-199 GJ/yr for gas, all bands for electricity) with all
taxes included, half-yearly since ~2007. Electricity production mix
(``nrg_ind_peh``) is annual gross production by source.

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

PRODUCTION_SOURCES: dict[str, str] = {
    "TOTAL": "total", "CF": "combustible_fuels", "RA100": "hydro", "RA300": "wind",
    "RA400": "solar", "N9000": "nuclear",
}


def _half_year_period(time_code: str):
    """Eurostat half-year codes look like ``2024-S1``/``2024-S2`` — map onto
    _period_from_time_code's monthly form by picking a representative month
    (January for H1, July for H2)."""
    fixed = time_code.replace("-S1", "-01").replace("-S2", "-07")
    return _period_from_time_code(fixed)


def _row(period, country_iso3: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _gas_price_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, "nrg_cons": "GJ20-199",
              "unit": "KWH", "tax": "I_TAX", "currency": "EUR", "sinceTimePeriod": "2000"}
    resp = ctx.http.get(f"{BASE}/nrg_pc_202", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _half_year_period(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "gas_price_eur_per_kwh", value, "EUR/kWh"))
    return rows


def _electricity_price_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, "nrg_cons": "TOT_KWH",
              "unit": "KWH", "tax": "I_TAX", "currency": "EUR", "sinceTimePeriod": "2000"}
    resp = ctx.http.get(f"{BASE}/nrg_pc_204", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _half_year_period(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, "electricity_price_eur_per_kwh", value, "EUR/kWh"))
    return rows


def _production_mix_rows(ctx: Ctx) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, "plants": "ELC",
              "operator": "TOTAL", "nrg_bal": "GEP", "unit": "GWH", "sinceTimePeriod": "2000"}
    resp = ctx.http.get(f"{BASE}/nrg_ind_peh", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        source_slug = PRODUCTION_SOURCES.get(dims.get("siec", ""))
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if source_slug is None or iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"electricity_production_gwh_{source_slug}", value, "GWh"))
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
            log.warning("eurostat_energy: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_energy: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_energy: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("gas_price", _gas_price_rows),
        ("electricity_price", _electricity_price_rows),
        ("production_mix", _production_mix_rows),
    ))
    if not rows:
        raise RuntimeError("eurostat_energy: every upstream failed")
    log.info("eurostat_energy: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_energy",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: household gas and "
        "electricity tariffs (half-yearly, since ~2007) and electricity production "
        "mix by source (annual, since 2000)."
    ),
)

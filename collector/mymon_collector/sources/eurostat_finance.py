"""Public finance, wages and trade for Germany, Italy, Spain, Greece, Turkey, France
*and the Netherlands*. Government debt/deficit, minimum wage, and goods+services
exports/imports were all completely uncovered before this module — grouped together
here (and on one combined dashboard per country) rather than as four separate
near-empty modules.

The Netherlands is included here (unlike most eurostat_* modules, which stick to the
six non-NL countries and leave NL to its own CBS-sourced modules) because these three
topics have no NL-specific source in this project and Eurostat's own numbers for the
Netherlands are the same EU-harmonized data as for the other six — there's no
"national" source being skipped in favour of a worse one. GEO_TO_ISO3 here is a local
superset of eurostat_metrics.GEO_TO_ISO3 (own HTTP calls, not the shared
``_eurostat_get``, precisely so adding NL here doesn't cascade into every other
eurostat_* module that imports the six-country dict).

Confirmed live, real per-indicator gaps (not bugs): government debt/deficit has no
Turkey data (ESA2010 government finance statistics are an EU/euro-area framework Turkey
doesn't report under); minimum wage has no Italy data (Italy has no statutory minimum
wage, a real fact, not a missing query).
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


def _row(period, country_iso3: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _half_year_period(time_code: str):
    """``2024-S1``/``2024-S2`` -> a representative month (January / July)."""
    fixed = time_code.replace("-S1", "-01").replace("-S2", "-07")
    return _period_from_time_code(fixed)


def _single_series_rows(
    ctx: Ctx, dataset: str, params: dict[str, Any], indicator: str, unit: str,
    period_fn=_period_from_time_code,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dims, value in _eurostat_get(ctx, dataset, params):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = period_fn(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, indicator, value, unit))
    return rows


# --------------------------------------------------------------------- government finance


def _govt_debt_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "gov_10dd_edpt1", {"sector": "S13", "na_item": "GD", "unit": "PC_GDP"},
        "govt_debt_pct_gdp", "%")


def _govt_deficit_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "gov_10dd_edpt1", {"sector": "S13", "na_item": "B9", "unit": "PC_GDP"},
        "govt_deficit_pct_gdp", "%")


# --------------------------------------------------------------------------------- wages


def _minimum_wage_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "earn_mw_cur", {"currency": "EUR"}, "minimum_wage_eur_month", "EUR",
        period_fn=_half_year_period)


# --------------------------------------------------------------------------------- trade


def _exports_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "nama_10_gdp", {"na_item": "P6", "unit": "CP_MEUR"},
        "exports_goods_services_meur", "million EUR")


def _imports_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "nama_10_gdp", {"na_item": "P7", "unit": "CP_MEUR"},
        "imports_goods_services_meur", "million EUR")


# --------------------------------------------------------------------------------- source


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("eurostat_finance: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_finance: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_finance: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("govt_debt", _govt_debt_rows),
        ("govt_deficit", _govt_deficit_rows),
        ("minimum_wage", _minimum_wage_rows),
        ("exports", _exports_rows),
        ("imports", _imports_rows),
    ))
    if not rows:
        raise RuntimeError("eurostat_finance: every upstream failed")
    log.info("eurostat_finance: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_finance",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France and the Netherlands via "
        "Eurostat: government debt and deficit as % of GDP, statutory minimum wage "
        "in EUR, and goods+services exports/imports in million EUR."
    ),
)

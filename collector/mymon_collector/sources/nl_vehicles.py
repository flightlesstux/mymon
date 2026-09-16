"""Netherlands passenger-car fleet by fuel type, and marinas/yacht harbours: CBS
StatLine, same OData v3 mechanism as nl_metrics.py.

Car fleet: two tables covering the active passenger-car stock (not new sales — CBS has
no simple "new registrations by fuel type" series; the discontinued car-importer
turnover index isn't a fuel-type breakdown either) as of 1 January each year, split by
fuel type (petrol/diesel/LPG/electric/CNG): 71405ned (2000-2022) and its successor
85237NED (2019-2026, same column layout) — both land in the same
``vehicle_fleet_<fuel>`` indicators, upsert-deduped on the overlap years.

Marinas: 84133NED (capacity — marina count, berths, visitor overnight stays; irregular
survey years 2015/2018/2020/2021) and 84132NED (financials/employment; 1997-2021, every
2-3 years). Both discontinued after 2021 — CBS simply stopped running the survey; not a
gap in this collector.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "price_index"
COUNTRY = "NLD"
CBS_BASE = "https://opendata.cbs.nl/ODataApi/odata"

FUEL_COLUMNS: dict[str, str] = {
    "Benzine_15": "petrol",
    "Diesel_16": "diesel",
    "LPG_17": "lpg",
    "Elektriciteit_18": "electric",
    "CNG_19": "cng",
}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _row(period: date, indicator: str, value: float, unit: str, source: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": COUNTRY,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": source,
    }


def _cbs_period(value: str) -> date | None:
    s = (value or "").strip()
    if len(s) != 8:
        return None
    if s[4:6] == "JJ":
        try:
            return date(int(s[:4]), 1, 1)
        except ValueError:
            return None
    return None


def _cbs_get(ctx: Ctx, table: str, filt: str | None = None) -> list[dict[str, Any]]:
    url = f"{CBS_BASE}/{table}/TypedDataSet"
    params = {"$format": "json"}
    if filt:
        params["$filter"] = filt
    resp = ctx.http.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    value = data.get("value")
    if not isinstance(value, list):
        raise ValueError(f"CBS {table}: unexpected payload shape")
    return value


# --------------------------------------------------------------------------- CBS: car fleet


def _fleet_rows_from(ctx: Ctx, table: str, total_code: str, dimension: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = f"{dimension} eq '{total_code}'"
    for rec in _cbs_get(ctx, table, filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        total = _num(rec.get("TotaalNederland_1"))
        if total is not None:
            rows.append(_row(period, "vehicle_fleet_total", total, "count", "cbs"))
        for col, fuel in FUEL_COLUMNS.items():
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, f"vehicle_fleet_{fuel}", value, "count", "cbs"))
    return rows


def _fleet_rows_old(ctx: Ctx) -> list[dict[str, Any]]:
    return _fleet_rows_from(ctx, "71405ned", "T001378", "Bouwjaren")


def _fleet_rows_new(ctx: Ctx) -> list[dict[str, Any]]:
    return _fleet_rows_from(ctx, "85237NED", "T001378", "Bouwjaar")


# --------------------------------------------------------------------------- CBS: marinas


def _marina_capacity_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "Jachthavens eq 'T001416'"
    for rec in _cbs_get(ctx, "84133NED", filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for col, indicator in (
            ("TotaalJachthavens_1", "marina_count"),
            ("TotaalZomerligplaatsen_2", "marina_berths"),
            ("TotaalPassantenovernachtingen_6", "marina_visitor_overnight_stays"),
        ):
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, "count", "cbs"))
    return rows


def _marina_finance_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "84132NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for col, indicator, unit in (
            ("TotaalWerkzamePersonen_5", "marina_employees", "count"),
            ("TotaalBaten_11", "marina_revenue_mln_eur", "million EUR"),
        ):
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, unit, "cbs"))
    return rows


# --------------------------------------------------------------------------- source


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("nl_vehicles: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("nl_vehicles: %s returned no rows", name)
            failures += 1
            continue
        log.info("nl_vehicles: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        seen[(r["period_date"], r["country_iso3"], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("fleet_old", _fleet_rows_old),
        ("fleet_new", _fleet_rows_new),  # runs after fleet_old so it wins the overlap dedupe
        ("marina_capacity", _marina_capacity_rows),
        ("marina_finance", _marina_finance_rows),
    ))
    if not rows:
        raise RuntimeError("nl_vehicles: every upstream failed")
    log.info("nl_vehicles: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, _dedupe(rows))]


SOURCE = Source(
    name="nl_vehicles",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Netherlands passenger-car fleet by fuel type (petrol/diesel/LPG/electric/"
        "CNG), annual since 2000, plus marina capacity (berths, visitor overnight "
        "stays) and finances, irregular survey years 1997-2021."
    ),
)

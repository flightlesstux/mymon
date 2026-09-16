"""Netherlands agriculture: CBS StatLine, same OData v3 mechanism as nl_metrics.py.

National figures (``81302ned``) land in ``price_index``; the same table exists split by
province (``80780ned``) and lands in ``region_metric`` (reusing the province rows already
seeded for house prices in nl_metrics.py — same PV20-PV31 codes, same client-side
``startswith("PV")`` filter, since RegioS also carries national/landsdeel/municipality
rows in the same dataset that aren't wanted here).

Both tables are annual, national back to 2000, regional depths vary by column but
generally 2000+ too. Every run re-pulls full history, no separate backfill.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "price_index"
REGION_TABLE = "region_metric"
COUNTRY = "NLD"
CBS_BASE = "https://opendata.cbs.nl/ODataApi/odata"

# Column key -> (indicator, unit). Same column names/suffixes in both 81302ned (national)
# and 80780ned (regional) — confirmed live, both tables share the same schema layout.
COLUMNS: dict[str, tuple[str, str]] = {
    "AantalLandbouwbedrijvenTotaal_1": ("farm_count", "count"),
    "CultuurgrondTotaal_3": ("agricultural_land", "ha"),
    "Akkerbouw_4": ("arable_land", "ha"),
    "TuinbouwOpenGrond_5": ("horticulture_open", "ha"),
    "TuinbouwOnderGlas_6": ("horticulture_glass", "ha"),
    "GraslandEnGroenvoedergewassen_7": ("grassland", "ha"),
    "RundveeTotaal_466": ("cattle_count", "count"),
    "VarkensTotaal_573": ("pig_count", "count"),
    "KippenTotaal_591": ("chicken_count", "count"),
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


def _region_row(
    period: date, region_code: str, indicator: str, value: float, unit: str
) -> dict[str, Any]:
    return {
        "period_date": period,
        "region_code": region_code,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "cbs",
    }


def _cbs_period(value: str) -> date | None:
    s = (value or "").strip()
    if len(s) != 8:
        return None
    if s[4:6] == "KW":
        try:
            year, q = int(s[:4]), int(s[6:8])
        except ValueError:
            return None
        if q not in (1, 2, 3, 4):
            return None
        return date(year, (q - 1) * 3 + 1, 1)
    try:
        year = int(s[:4])
    except ValueError:
        return None
    if s[4:6] == "MM":
        try:
            return date(year, int(s[6:8]), 1)
        except ValueError:
            return None
    if s[4:6] == "JJ":
        return date(year, 1, 1)
    return None


def _cbs_get(ctx: Ctx, table: str) -> list[dict[str, Any]]:
    resp = ctx.http.get(f"{CBS_BASE}/{table}/TypedDataSet", params={"$format": "json"})
    resp.raise_for_status()
    data = resp.json()
    value = data.get("value")
    if not isinstance(value, list):
        raise ValueError(f"CBS {table}: unexpected payload shape")
    return value


def _national_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "81302ned"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for col, (indicator, unit) in COLUMNS.items():
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, unit, "cbs"))
    return rows


def _regional_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "80780ned"):
        region_code = (rec.get("RegioS") or "").strip()
        if not region_code.startswith("PV"):
            continue
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for col, (indicator, _unit) in COLUMNS.items():
            value = _num(rec.get(col))
            if value is not None:
                # 80780ned reports land use in "are" (1 ha = 100 are), not "ha" like
                # 81302ned — pass the native unit through honestly rather than convert.
                unit = "are" if _unit == "ha" else _unit
                rows.append(_region_row(period, region_code, indicator, value, unit))
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
            log.warning("nl_agriculture: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("nl_agriculture: %s returned no rows", name)
            failures += 1
            continue
        log.info("nl_agriculture: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def _dedupe(rows: list[dict[str, Any]], key_field: str) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        seen[(r["period_date"], r[key_field], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    country_rows, country_failures = _run_upstreams(ctx, (("national", _national_rows),))
    region_rows, region_failures = _run_upstreams(ctx, (("regional", _regional_rows),))
    if not country_rows and not region_rows:
        raise RuntimeError("nl_agriculture: every upstream failed")
    log.info("nl_agriculture: %d country rows (%d failures), %d region rows (%d failures)",
              len(country_rows), country_failures, len(region_rows), region_failures)
    return [
        (TABLE, _dedupe(country_rows, "country_iso3")),
        (REGION_TABLE, _dedupe(region_rows, "region_code")),
    ]


SOURCE = Source(
    name="nl_agriculture",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE, REGION_TABLE],
    description=(
        "Netherlands agriculture: CBS farm count, land use (arable/horticulture/"
        "grassland) and livestock (cattle/pigs/chickens), national and by province, "
        "annual since 2000."
    ),
)

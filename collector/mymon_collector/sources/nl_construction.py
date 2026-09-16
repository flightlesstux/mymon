"""Netherlands construction sector, plus bankruptcies across the whole economy: CBS
StatLine, same OData v3 mechanism as nl_metrics.py.

Construction: turnover index (85809NED, since 2005), input cost index split into wage/
material components (80444ned, since 1990), output cost index incl./excl. VAT (80334ned,
since 1914 — the deepest history in the entire collector), and building permits count +
cost (83667NED, since 2012).

Bankruptcies: headline monthly count for businesses (82242NED, since 1981) plus a
13-sector breakdown (82244NED, since 2009) landing as ``bankruptcies_sector_<slug>`` — a
suffix-per-series pattern rather than a new dimension table, matching how nl_metrics.py
already handles the labour-market age/gender breakdown.

Every table is small; each run re-pulls full history, no separate backfill.
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

# CBS top-level SBI 2008 sector codes (82244NED), padded to 7 chars per that table's
# BedrijfstakkenBranchesSBI2008 dimension -> our indicator slug
BANKRUPTCY_SECTORS: dict[str, str] = {
    "301000 ": "agriculture",
    "307500 ": "industry",
    "350000 ": "construction",
    "354200 ": "trade",
    "383100 ": "transport",
    "389100 ": "hospitality",
    "391600 ": "ict",
    "396300 ": "finance",
    "402000 ": "real_estate",
    "403300 ": "business_services",
    "410200 ": "other_business_services",
    "422400 ": "healthcare",
    "428100 ": "culture_sport_recreation",
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
    """CBS months look like ``2025MM01``, quarters ``2025KW02``, years ``2025JJ00``."""
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


# --------------------------------------------------------------------------- CBS: turnover
#
# 85809NED — quarterly construction sector turnover index, all businesses with 1+
# employee (WP19077), whole construction sector (350000).

def _turnover_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "Bedrijfsgrootte eq 'WP19077' and BedrijfstakkenBranchesSBI2008 eq '350000'"
    for rec in _cbs_get(ctx, "85809NED", filt):
        raw = rec.get("Perioden") or ""
        if raw[4:6] != "MM":
            continue  # also carries quarterly (KW) rollups of the same series — see
            # _bankruptcy_total_rows for why mixing granularities silently collides
        period = _cbs_period(raw)
        if period is None:
            continue
        idx = _num(rec.get("IndexcijfersOmzet_1"))
        if idx is not None:
            rows.append(_row(period, "construction_turnover_index", idx, "2021=100", "cbs"))
        yoy = _num(rec.get("OmzetontwikkelingTOVEenJaarEerder_2"))
        if yoy is not None:
            rows.append(_row(period, "construction_turnover_yoy_pct", yoy, "%", "cbs"))
    return rows


# ------------------------------------------------------------- CBS: building cost, input
#
# 80444ned — monthly input cost index (what it costs to build), split into wage and
# material components. Flat table, no dimension filtering. Back to 1990.

def _building_cost_input_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "80444ned"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for col, indicator in (
            ("Prijsindex_1", "building_cost_input_index"),
            ("Prijsindex_3", "building_cost_input_wage_index"),
            ("Prijsindex_5", "building_cost_input_material_index"),
        ):
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, "2000=100", "cbs"))
    return rows


# ------------------------------------------------------------ CBS: building cost, output
#
# 80334ned — building cost output price index, incl./excl. VAT. Flat table. Back to
# 1914 — the deepest history of any series in this collector. From 1950 it carries both
# annual (JJ00) and quarterly (KW) rows for the same years; KW01 maps to the same 1st-
# of-year date as JJ00, so only the annual rows are kept (also the only granularity
# available before 1950, so this keeps the full 1914+ depth on one consistent cadence).

def _building_cost_output_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "80334ned"):
        raw = rec.get("Perioden") or ""
        if raw[4:6] != "JJ":
            continue
        period = _cbs_period(raw)
        if period is None:
            continue
        incl_vat = _num(rec.get("Index_1"))
        if incl_vat is not None:
            rows.append(_row(period, "building_cost_output_index_incl_vat", incl_vat,
                              "2000=100", "cbs"))
        excl_vat = _num(rec.get("Index_3"))
        if excl_vat is not None:
            rows.append(_row(period, "building_cost_output_index_excl_vat", excl_vat,
                              "2000=100", "cbs"))
    return rows


# --------------------------------------------------------------- CBS: building permits
#
# 83667NED — monthly building permits, count + cost, all work types (T001212) and all
# building purposes (T001032). Back to 2012.

def _building_permits_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "AardWerkzaamheden eq 'T001212' and Gebouwbestemming eq 'T001032'"
    for rec in _cbs_get(ctx, "83667NED", filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        cost = _num(rec.get("Bouwkosten_1"))
        if cost is not None:
            rows.append(_row(period, "building_permits_cost_mln_eur", cost, "million EUR", "cbs"))
        count = _num(rec.get("Bouwvergunningen_2"))
        if count is not None:
            rows.append(_row(period, "building_permits_count", count, "count", "cbs"))
    return rows


# --------------------------------------------------------------------- CBS: bankruptcies
#
# 82242NED — monthly bankruptcy count, businesses and institutions only (A047597, not
# natural persons). Back to 1981.

def _bankruptcy_total_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "TypeGefailleerde eq 'A047597'"
    for rec in _cbs_get(ctx, "82242NED", filt):
        raw = rec.get("Perioden") or ""
        if raw[4:6] != "MM":
            continue  # this table also carries quarterly (KW) rollups of the same series;
            # KW01 maps to the same 1st-of-year date as MM01, so mixing them would silently
            # let one clobber the other via the upsert PK
        period = _cbs_period(raw)
        if period is None:
            continue
        count = _num(rec.get("UitgesprokenFaillissementen_1"))
        if count is not None:
            rows.append(_row(period, "bankruptcies_total", count, "count", "cbs"))
    return rows


# 82244NED — same headline figure, broken down by 13 top-level economic sectors.
# TypeGefailleerde=A047596 (companies, institutions and sole proprietorships combined —
# the broadest "businesses" total this table offers).

def _bankruptcy_sector_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sbi_code, slug in BANKRUPTCY_SECTORS.items():
        filt = f"TypeGefailleerde eq 'A047596' and BedrijfstakkenBranchesSBI2008 eq '{sbi_code}'"
        for rec in _cbs_get(ctx, "82244NED", filt):
            raw = rec.get("Perioden") or ""
            if raw[4:6] != "MM":
                continue  # see _bankruptcy_total_rows — same table mixes MM and KW periods
            period = _cbs_period(raw)
            if period is None:
                continue
            count = _num(rec.get("UitgesprokenFaillissementen_1"))
            if count is not None:
                rows.append(_row(period, f"bankruptcies_sector_{slug}", count, "count", "cbs"))
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
            log.warning("nl_construction: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("nl_construction: %s returned no rows", name)
            failures += 1
            continue
        log.info("nl_construction: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        seen[(r["period_date"], r["country_iso3"], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("turnover", _turnover_rows),
        ("building_cost_input", _building_cost_input_rows),
        ("building_cost_output", _building_cost_output_rows),
        ("building_permits", _building_permits_rows),
        ("bankruptcy_total", _bankruptcy_total_rows),
        ("bankruptcy_sector", _bankruptcy_sector_rows),
    ))
    if not rows:
        raise RuntimeError("nl_construction: every upstream failed")
    log.info("nl_construction: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, _dedupe(rows))]


SOURCE = Source(
    name="nl_construction",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Netherlands construction: turnover index, building cost (input wage/material "
        "components since 1990, output incl./excl. VAT since 1914) and building "
        "permits. Plus economy-wide bankruptcies, headline since 1981 and split across "
        "13 sectors since 2009."
    ),
)

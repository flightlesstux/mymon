"""Netherlands-specific indicators: CBS (Statistics Netherlands) StatLine and the ECB.

Everything lands in ``price_index`` (PK ``period_date, country_iso3, indicator, source``),
``country_iso3='NLD'``. CBS's OData v3 API (``opendata.cbs.nl``) needs no key and each table
here is small (a few hundred rows), so every run re-pulls full history and there is no
separate backfill — same pattern as ``price_indices.py``.

CBS tables used (probed live 2026-09, table IDs are stable CBS identifiers):
- ``83131NED`` Consumentenprijzen (CPI): category ``T001112`` (all spending) for headline
  CPI + YoY inflation, ``CPI011000`` (Voedingsmiddelen) for food-only CPI, plus the index
  value (no YoY) for each of the 12 top-level COICOP spending categories (housing/energy,
  transport, health, education, ...) — a cost-of-living breakdown.
- ``85773NED`` Bestaande koopwoningen (existing home sales): price index, average sale
  price, month's transaction count.
- ``70675ned`` Huurverhoging woningen (annual rent increase, all landlords), 1959-present.
- ``85592NED`` Gemiddelde energietarieven (average consumer energy tariffs): gas
  (Euro/m3, columns 1-6) and electricity (Euro/kWh, columns 7-15) variable contract price,
  incl. VAT (``Btw='A048944'``).
- ``80590ned`` Arbeidsdeelname en werkloosheid: seasonally adjusted unemployment rate,
  total population 15-75 (``Geslacht='T001038'``, ``Leeftijd='52052'``).
- ``82058NED`` Logiesaccommodaties (tourism): total hotel/accommodation guests and
  overnight stays, all accommodation types.

Interest rate: ECB Data Portal ``IRS`` dataflow, the Dutch 10-year government bond yield
("long-term interest rate for convergence purposes") — same SDMX CSV mechanism already
used by ``reserves_ecb.py``.

Netherlands-specific things that turned out NOT to be freely available (checked live,
2026-09): current mortgage/deposit interest rates (no public API found for DNB or CBS
current series) and road traffic congestion (NDW's open data is a live DATEX II XML
snapshot with no historical query API; ANWB's traffic page is a JS-rendered app with no
public API). Neither is faked here.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "price_index"
COUNTRY = "NLD"

CBS_BASE = "https://opendata.cbs.nl/ODataApi/odata"
ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/IRS/"
    "M.NL.L.L40.CI.0000.EUR.N.Z?format=csvdata"
)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


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
    """CBS months look like ``2025MM01``, years like ``2025JJ00``."""
    s = (value or "").strip()
    if len(s) != 8:
        return None
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


# --------------------------------------------------------------------------- CBS: CPI

# The 12 top-level COICOP spending categories CBS breaks the CPI into. Slugs are used
# directly as `price_index.indicator` (as `cpi_cat_<slug>`) and are readable enough to use
# as-is for a dashboard legend — no separate label lookup needed.
CPI_CATEGORIES: dict[str, str] = {
    "CPI010000": "food_and_drink",
    "CPI020000": "alcohol_and_tobacco",
    "CPI030000": "clothing_and_footwear",
    "CPI040000": "housing_water_energy",
    "CPI050000": "furnishings_household",
    "CPI060000": "health",
    "CPI070000": "transport",
    "CPI080000": "communication",
    "CPI090000": "recreation_and_culture",
    "CPI100000": "education",
    "CPI110000": "restaurants_and_hotels",
    "CPI120000": "misc_goods_and_services",
}


def _cpi_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # (CBS category code, index indicator name, YoY indicator name or None)
    headline = [
        ("T001112  ", "cpi_index", "cpi_inflation_pct"),
        ("CPI011000", "food_cpi_index", "food_cpi_inflation_pct"),
    ]
    categories = [(code, f"cpi_cat_{slug}", None) for code, slug in CPI_CATEGORIES.items()]
    for code, index_name, inflation_name in headline + categories:
        recs = _cbs_get(ctx, "83131NED", f"Bestedingscategorieen eq '{code}'")
        for rec in recs:
            period = _cbs_period(rec.get("Perioden"))
            if period is None:
                continue
            idx = _num(rec.get("CPI_1"))
            if idx is not None:
                rows.append(_row(period, index_name, idx, "2015=100", "cbs"))
            if inflation_name:
                yoy = _num(rec.get("JaarmutatieCPI_5"))
                if yoy is not None:
                    rows.append(_row(period, inflation_name, yoy, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: rent


def _rent_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "70675ned"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        value = _num(rec.get("Huurverhoging_1"))
        if value is not None:
            rows.append(_row(period, "rent_increase_pct", value, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: house prices


def _house_price_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "85773NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        idx = _num(rec.get("PrijsindexVerkoopprijzen_1"))
        if idx is not None:
            rows.append(_row(period, "house_price_index", idx, "2020=100", "cbs"))
        avg = _num(rec.get("GemiddeldeVerkoopprijs_7"))
        if avg is not None:
            rows.append(_row(period, "house_price_avg_eur", avg, "EUR", "cbs"))
        sold = _num(rec.get("VerkochteWoningen_4"))
        if sold is not None:
            rows.append(_row(period, "house_sales_count", sold, "count", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: energy tariffs


def _energy_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "85592NED", "Btw eq 'A048944'"):  # incl. VAT
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        gas = _num(rec.get("VariabelLeveringstariefContractprijs_3"))
        if gas is not None:
            rows.append(_row(period, "gas_variable_price_eur_m3", gas, "EUR/m3", "cbs"))
        elec = _num(rec.get("VariabelLeveringstariefContractprijs_9"))
        if elec is not None:
            rows.append(_row(period, "electricity_variable_price_eur_kwh", elec, "EUR/kWh", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: unemployment


def _unemployment_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "Geslacht eq 'T001038' and Leeftijd eq '52052   '"
    for rec in _cbs_get(ctx, "80590ned", filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        rate = _num(rec.get("Seizoengecorrigeerd_8"))
        if rate is not None:
            rows.append(_row(period, "unemployment_rate_pct", rate, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: tourism


def _tourism_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "82058NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        guests = _num(rec.get("Totaal_1"))
        if guests is not None:
            rows.append(_row(period, "tourism_guests_thousands", guests, "x1000", "cbs"))
        stays = _num(rec.get("Totaal_4"))
        if stays is not None:
            rows.append(_row(period, "tourism_overnight_stays_thousands", stays, "x1000", "cbs"))
        occ = _num(rec.get("Bezettingsgraad_7"))
        if occ is not None:
            rows.append(_row(period, "tourism_occupancy_pct", occ, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- ECB: bond yield


def _bond_yield_rows(ctx: Ctx) -> list[dict[str, Any]]:
    resp = ctx.http.get(ECB_URL)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "TIME_PERIOD" not in reader.fieldnames:
        raise ValueError(f"ECB IRS CSV missing columns, got {reader.fieldnames}")
    rows: list[dict[str, Any]] = []
    for rec in reader:
        period_str = (rec.get("TIME_PERIOD") or "").strip()
        try:
            year, month = period_str.split("-")
            period = date(int(year), int(month), 1)
        except (ValueError, TypeError):
            continue
        value = _num(rec.get("OBS_VALUE"))
        if value is None:
            continue
        rows.append(_row(period, "gov_bond_10y_pct", value, "%", "ecb"))
    return rows


# --------------------------------------------------------------------------- source


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict] = {}
    for r in rows:
        seen[(r["period_date"], r["country_iso3"], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    rows: list[dict[str, Any]] = []
    failures = 0
    upstreams = (
        ("cpi", _cpi_rows),
        ("rent", _rent_rows),
        ("house_prices", _house_price_rows),
        ("energy", _energy_rows),
        ("unemployment", _unemployment_rows),
        ("tourism", _tourism_rows),
        ("bond_yield", _bond_yield_rows),
    )
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("nl_metrics: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("nl_metrics: %s returned no rows", name)
            failures += 1
            continue
        log.info("nl_metrics: %s -> %d rows", name, len(part))
        rows.extend(part)
    if not rows:
        raise RuntimeError("nl_metrics: every upstream failed")
    return [(TABLE, _dedupe(rows))]


SOURCE = Source(
    name="nl_metrics",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Netherlands: CBS CPI/food CPI, house prices, energy tariffs, unemployment, "
        "tourism, plus the ECB's Dutch 10-year government bond yield."
    ),
)

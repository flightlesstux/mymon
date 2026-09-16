"""Germany, Italy, Spain, France and Greece: 10-year government bond yield and actual
bank lending/deposit rates, via the ECB Data Portal — same SDMX CSV mechanism and same
IRS/MIR dataflows already used for the Netherlands in nl_metrics.py, just five more
country codes. Not Turkey — not part of the euro area, so neither dataflow covers it
(Turkey's own central bank policy rate is already collected separately via
bis_policy_rates).

ECB's own country codes are plain ISO 3166-1 alpha-2 (``GR`` for Greece, not Eurostat's
``EL`` quirk) — confirmed live, a Eurostat-style ``EL`` query 404s against ECB.

Monthly since whenever each series starts (varies by country); every run re-pulls full
history, no separate backfill needed — small CSVs.
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
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"

COUNTRIES: dict[str, str] = {"DE": "DEU", "IT": "ITA", "ES": "ESP", "FR": "FRA", "GR": "GRC"}

# ECB MIR series suffixes — see nl_metrics.py's ECB_MIR_KEYS for what these mean
# (A2C = new-business mortgage composite rate, L22 = overnight deposits, L23 = term
# deposits).
MIR_SUFFIXES: dict[str, str] = {
    "bank_mortgage_rate_pct": "A2C.A.R.A.2250",
    "bank_savings_rate_pct": "L22.A.R.A.2250",
    "bank_term_deposit_rate_pct": "L23.A.R.A.2250",
}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _row(period: date, iso3: str, indicator: str, value: float) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": iso3,
        "indicator": indicator,
        "value": value,
        "unit": "%",
        "source": "ecb",
    }


def _ecb_series_rows(ctx: Ctx, key: str, iso3: str, indicator: str) -> list[dict[str, Any]]:
    resp = ctx.http.get(f"{ECB_BASE}/{key}", params={"format": "csvdata"})
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "TIME_PERIOD" not in reader.fieldnames:
        raise ValueError(f"ECB {key} CSV missing columns, got {reader.fieldnames}")
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
        rows.append(_row(period, iso3, indicator, value))
    return rows


def _bond_yield_rows_for(ecb_cc: str, iso3: str):
    def _fetch(ctx: Ctx) -> list[dict[str, Any]]:
        key = f"IRS/M.{ecb_cc}.L.L40.CI.0000.EUR.N.Z"
        return _ecb_series_rows(ctx, key, iso3, "gov_bond_10y_pct")
    return _fetch


def _bank_rate_rows_for(ecb_cc: str, iso3: str):
    def _fetch(ctx: Ctx) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for indicator, suffix in MIR_SUFFIXES.items():
            key = f"MIR/M.{ecb_cc}.B.{suffix}.EUR.N"
            rows.extend(_ecb_series_rows(ctx, key, iso3, indicator))
        return rows
    return _fetch


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("ecb_country_rates: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("ecb_country_rates: %s returned no rows", name)
            failures += 1
            continue
        log.info("ecb_country_rates: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    upstreams: list[tuple[str, Any]] = []
    for ecb_cc, iso3 in COUNTRIES.items():
        upstreams.append((f"{ecb_cc}_bond_yield", _bond_yield_rows_for(ecb_cc, iso3)))
        upstreams.append((f"{ecb_cc}_bank_rates", _bank_rate_rows_for(ecb_cc, iso3)))
    rows, failures = _run_upstreams(ctx, tuple(upstreams))
    if not rows:
        raise RuntimeError("ecb_country_rates: every upstream failed")
    log.info("ecb_country_rates: %d rows (%d/%d upstream failures)",
              len(rows), failures, len(upstreams))
    return [(TABLE, rows)]


SOURCE = Source(
    name="ecb_country_rates",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, France, Greece: 10-year government bond yield and "
        "actual bank mortgage/savings/term-deposit rates, via the ECB — same "
        "mechanism as NL's bank rates, monthly."
    ),
)

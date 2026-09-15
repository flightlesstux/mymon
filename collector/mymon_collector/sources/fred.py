"""FRED (St. Louis Fed) source: US reserves, policy rate and CPI.

Endpoint (one call per series, ``file_type=json``)::

    https://api.stlouisfed.org/fred/series/observations
        ?series_id=<ID>&api_key=<KEY>&file_type=json&observation_start=1990-01-01

Response ``{"observations": [{"date": "YYYY-MM-DD", "value": "123.4" | "."}, ...]}``.
A value of ``"."`` marks a missing observation and is skipped.

Series:
- ``TRESEGUSM052N``  total reserves excluding gold, USD, monthly  -> ``reserves`` (metric
  ``ex_gold``)
- ``FEDFUNDS``       effective federal funds rate, %              -> ``price_index``
  (``policy_rate_pct``)
- ``CPIAUCSL``       CPI-U all items, index 1982-84=100, SA       -> ``price_index``
  (``cpi_index``)

The full history since 1990 is a few hundred monthly observations per series, so every run
fetches it whole; no separate backfill is needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
OBSERVATION_START = "1990-01-01"
SOURCE_NAME = "fred"
COUNTRY_ISO3 = "USA"
COUNTRY_NAME = "United States"


@dataclass(frozen=True)
class _Series:
    series_id: str
    table: str
    key: str  # metric (reserves) or indicator (price_index)
    unit: str = ""


SERIES: tuple[_Series, ...] = (
    _Series("TRESEGUSM052N", "reserves", "ex_gold"),
    _Series("FEDFUNDS", "price_index", "policy_rate_pct", "%"),
    _Series("CPIAUCSL", "price_index", "cpi_index", "index 1982-84=100"),
)


# --------------------------------------------------------------------------- helpers


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_value(value: Any) -> Decimal | None:
    """FRED encodes numbers as strings and missing observations as ``"."``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text == ".":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _observations(ctx: Ctx, series_id: str, api_key: str) -> list[dict[str, Any]]:
    resp = ctx.http.get(
        OBSERVATIONS_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": OBSERVATION_START,
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"fred: unexpected payload type for {series_id}")
    if "error_message" in payload:
        raise ValueError(f"fred: {series_id}: {payload['error_message']}")
    obs = payload.get("observations")
    if not isinstance(obs, list):
        raise ValueError(f"fred: no observations array for {series_id}")
    return obs


def _row(spec: _Series, day: date, value: Decimal) -> dict[str, Any]:
    if spec.table == "reserves":
        return {
            "period_date": day,
            "country_iso3": COUNTRY_ISO3,
            "country": COUNTRY_NAME,
            "metric": spec.key,
            "value_usd": value,
            "source": SOURCE_NAME,
        }
    return {
        "period_date": day,
        "country_iso3": COUNTRY_ISO3,
        "indicator": spec.key,
        "value": value,
        "unit": spec.unit,
        "source": SOURCE_NAME,
    }


# --------------------------------------------------------------------------- fetch


def fetch(ctx: Ctx) -> Rows:
    api_key = ctx.env("FRED_API_KEY")
    if not api_key:
        raise ValueError("fred: FRED_API_KEY is not set")

    by_table: dict[str, list[dict[str, Any]]] = {"reserves": [], "price_index": []}
    failures = 0
    for spec in SERIES:
        try:
            observations = _observations(ctx, spec.series_id, api_key)
        except Exception as exc:
            failures += 1
            log.warning("fred: %s request failed: %s", spec.series_id, exc)
            continue
        kept = 0
        for item in observations:
            if not isinstance(item, dict):
                log.warning("fred: %s: non-object observation skipped", spec.series_id)
                continue
            day = _parse_date(item.get("date"))
            if day is None:
                log.warning("fred: %s: bad date %r skipped", spec.series_id, item.get("date"))
                continue
            value = _parse_value(item.get("value"))
            if value is None:
                continue  # "." = not available for that period
            by_table[spec.table].append(_row(spec, day, value))
            kept += 1
        log.info("fred: %s -> %d rows", spec.series_id, kept)

    if failures == len(SERIES):
        raise ValueError("fred: every series request failed")
    return [(table, rows) for table, rows in by_table.items()]


SOURCE = Source(
    name="fred",
    interval=86400,
    fetch=fetch,
    backfill=None,
    requires_env=["FRED_API_KEY"],
    tables=["reserves", "price_index"],
    description="FRED: US total reserves ex gold, fed funds rate and CPI-U",
)

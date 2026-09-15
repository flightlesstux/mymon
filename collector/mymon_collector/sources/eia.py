"""EIA (US Energy Information Administration) v2 API source: US fuel and energy prices.

One request per series against the v2 ``data`` endpoints, e.g.::

    https://api.eia.gov/v2/petroleum/pri/gnd/data/?api_key=<KEY>&frequency=weekly
        &data[0]=value&facets[series][]=EMM_EPMR_PTE_NUS_DPG
        &sort[0][column]=period&sort[0][direction]=desc&length=5000

Response ``{"response": {"data": [{"period": "2025-09-08", "series": "...", "value": "3.199",
"units": "$/GAL", ...}, ...], "total": "..."}, "request": {...}, "apiVersion": "..."}``.
``value`` is a numeric string (occasionally ``null``); ``period`` is ``YYYY-MM-DD`` for weekly and
daily frequencies.

Series:
- ``EMM_EPMR_PTE_NUS_DPG``  weekly US regular gasoline retail -> ``fuel_price`` ``petrol_regular``
- ``EMD_EPD2D_PTE_NUS_DPG``  weekly US No 2 diesel retail      -> ``fuel_price`` ``diesel``
- ``RNGWHHD``               daily Henry Hub spot, USD/MMBtu   -> ``commodity_price`` ``henry_hub``
- ``RBRTE``                 daily Brent spot, USD/bbl         -> ``commodity_price`` ``brent_spot``
- ``RWTC``                  daily WTI spot, USD/bbl           -> ``commodity_price`` ``wti_spot``

``length=5000`` sorted by period descending returns the whole weekly history and ~20 years of
daily prices in one page, so every run refreshes the full window; no separate backfill.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE_URL = "https://api.eia.gov/v2"
PAGE_LENGTH = 5000
SOURCE_NAME = "eia"
COUNTRY_ISO2 = "US"


@dataclass(frozen=True)
class _Series:
    series_id: str
    route: str  # path under BASE_URL, without the trailing /data/
    frequency: str
    table: str
    key: str  # fuel_type or commodity
    unit: str


SERIES: tuple[_Series, ...] = (
    _Series(
        "EMM_EPMR_PTE_NUS_DPG",
        "petroleum/pri/gnd",
        "weekly",
        "fuel_price",
        "petrol_regular",
        "USD/gal",
    ),
    _Series(
        "EMD_EPD2D_PTE_NUS_DPG", "petroleum/pri/gnd", "weekly", "fuel_price", "diesel", "USD/gal"
    ),
    _Series("RNGWHHD", "natural-gas/pri/fut", "daily", "commodity_price", "henry_hub", "USD/MMBtu"),
    _Series("RBRTE", "petroleum/pri/spt", "daily", "commodity_price", "brent_spot", "USD/bbl"),
    _Series("RWTC", "petroleum/pri/spt", "daily", "commodity_price", "wti_spot", "USD/bbl"),
)


# --------------------------------------------------------------------------- helpers


def _parse_period(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _data(ctx: Ctx, spec: _Series, api_key: str) -> list[dict[str, Any]]:
    resp = ctx.http.get(
        f"{BASE_URL}/{spec.route}/data/",
        params={
            "api_key": api_key,
            "frequency": spec.frequency,
            "data[0]": "value",
            "facets[series][]": spec.series_id,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": PAGE_LENGTH,
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"eia: unexpected payload type for {spec.series_id}")
    if "error" in payload:
        raise ValueError(f"eia: {spec.series_id}: {payload['error']}")
    response = payload.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise ValueError(f"eia: no response.data array for {spec.series_id}")
    return response["data"]


def _row(spec: _Series, day: date, value: Decimal) -> dict[str, Any]:
    if spec.table == "fuel_price":
        return {
            "period_date": day,
            "country_iso2": COUNTRY_ISO2,
            "region": "",
            "fuel_type": spec.key,
            "price": value,
            "currency": "USD",
            "unit": spec.unit,
            "source": SOURCE_NAME,
        }
    return {
        "period_date": day,
        "commodity": spec.key,
        "price": value,
        "unit": spec.unit,
        "source": SOURCE_NAME,
    }


# --------------------------------------------------------------------------- fetch


def fetch(ctx: Ctx) -> Rows:
    api_key = ctx.env("EIA_API_KEY")
    if not api_key:
        raise ValueError("eia: EIA_API_KEY is not set")

    by_table: dict[str, list[dict[str, Any]]] = {"fuel_price": [], "commodity_price": []}
    failures = 0
    for spec in SERIES:
        try:
            data = _data(ctx, spec, api_key)
        except Exception as exc:
            failures += 1
            log.warning("eia: %s request failed: %s", spec.series_id, exc)
            continue
        seen: set[date] = set()
        for item in data:
            if not isinstance(item, dict):
                log.warning("eia: %s: non-object record skipped", spec.series_id)
                continue
            if item.get("series") not in (None, spec.series_id):
                continue  # facet mismatch, never expected
            day = _parse_period(item.get("period"))
            if day is None:
                log.warning("eia: %s: bad period %r skipped", spec.series_id, item.get("period"))
                continue
            value = _parse_value(item.get("value"))
            if value is None or day in seen:
                continue
            seen.add(day)
            by_table[spec.table].append(_row(spec, day, value))
        log.info("eia: %s -> %d rows", spec.series_id, len(seen))

    if failures == len(SERIES):
        raise ValueError("eia: every series request failed")
    return [(table, rows) for table, rows in by_table.items()]


SOURCE = Source(
    name="eia",
    interval=86400,
    fetch=fetch,
    backfill=None,
    requires_env=["EIA_API_KEY"],
    tables=["fuel_price", "commodity_price"],
    description="EIA: US gasoline/diesel retail, Henry Hub, Brent and WTI spot prices",
)

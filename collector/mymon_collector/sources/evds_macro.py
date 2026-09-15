"""TCMB EVDS source: Turkish consumer price index.

Endpoint. The service moved from ``evds2.tcmb.gov.tr/service/evds/`` (now a 302 to the web
UI) to::

    https://evds3.tcmb.gov.tr/igmevdsms-dis/series=<CODES>&startDate=dd-mm-yyyy&endDate=dd-mm-yyyy&type=json

The query is part of the path (no leading ``?``) and the API key travels in the ``key`` HTTP
header. Verified live without a key: the URL answers ``401 Invalid API Key`` as plain text.

Response ``{"totalCount": N, "items": [{"Tarih": "2010-1", "TP_FG_J0": "174.07",
"UNIXTIME": {"$numberLong": "..."}}, ...]}``. Series codes are requested with dots and come
back with underscores. ``Tarih`` is ``YYYY-M`` for monthly series but ``dd-mm-yyyy`` for daily
ones; both are accepted. A value may be ``null``/empty for unpublished periods and is skipped.

Series (all country ``TUR``, source ``tcmb_evds``):
- ``TP.FG.J0``  CPI, general index, 2003=100, monthly -> ``price_index`` indicator ``cpi_index``

Only the CPI series is shipped. The CBRT one-week repo (policy) rate could not be mapped to an
EVDS series code with confidence (``TP.APIFON4`` is the weighted average funding cost, not the
policy rate); add it to ``SERIES`` once the code is confirmed against a live key. The policy
rate for Türkiye is meanwhile available from the ``bis_policy_rates`` source.

History since 2010 is ~200 monthly rows, so each run fetches the whole range.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
START_DATE = "01-01-2010"
SOURCE_NAME = "tcmb_evds"
COUNTRY_ISO3 = "TUR"


@dataclass(frozen=True)
class _Series:
    code: str  # request form, dotted
    indicator: str
    unit: str

    @property
    def column(self) -> str:
        return self.code.replace(".", "_")


SERIES: tuple[_Series, ...] = (_Series("TP.FG.J0", "cpi_index", "index 2003=100"),)

_YM = re.compile(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$")  # 2010-1 | 2010-01 | 2010-01-15
_DMY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")  # 15-01-2010


# --------------------------------------------------------------------------- helpers


def _parse_period(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        m = _YM.match(text)
        if m:
            year, month, day = int(m[1]), int(m[2]), int(m[3] or 1)
            return date(year, month, day)
        m = _DMY.match(text)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None
    return None


def _parse_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def build_url(codes: list[str], start: str, end: str) -> str:
    return f"{BASE_URL}series={'-'.join(codes)}&startDate={start}&endDate={end}&type=json"


def _items(ctx: Ctx, api_key: str) -> list[dict[str, Any]]:
    url = build_url([s.code for s in SERIES], START_DATE, ctx.now.strftime("%d-%m-%Y"))
    resp = ctx.http.get(url, headers={"key": api_key})
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ValueError(f"evds_macro: non-JSON response: {resp.text[:120]!r}") from exc
    if not isinstance(payload, dict):
        raise ValueError("evds_macro: unexpected payload type")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("evds_macro: no items array in response")
    return items


# --------------------------------------------------------------------------- fetch


def fetch(ctx: Ctx) -> Rows:
    api_key = ctx.env("EVDS_API_KEY")
    if not api_key:
        raise ValueError("evds_macro: EVDS_API_KEY is not set")

    rows: list[dict[str, Any]] = []
    for item in _items(ctx, api_key):
        if not isinstance(item, dict):
            log.warning("evds_macro: non-object item skipped")
            continue
        period = _parse_period(item.get("Tarih"))
        if period is None:
            log.warning("evds_macro: bad Tarih %r skipped", item.get("Tarih"))
            continue
        for spec in SERIES:
            value = _parse_value(item.get(spec.column))
            if value is None:
                continue
            rows.append(
                {
                    "period_date": period,
                    "country_iso3": COUNTRY_ISO3,
                    "indicator": spec.indicator,
                    "value": value,
                    "unit": spec.unit,
                    "source": SOURCE_NAME,
                }
            )
    if not rows:
        raise ValueError("evds_macro: response contained no usable observations")
    log.info("evds_macro: %d rows", len(rows))
    return [("price_index", rows)]


SOURCE = Source(
    name="evds_macro",
    interval=86400,
    fetch=fetch,
    backfill=None,
    requires_env=["EVDS_API_KEY"],
    tables=["price_index"],
    description="TCMB EVDS: Turkish CPI (2003=100)",
)

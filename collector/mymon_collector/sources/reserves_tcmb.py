"""Turkiye weekly international reserves from the TCMB EVDS web service.

Probe notes (2026-09): the public TCMB statistics pages (International Reserves and
Foreign Currency Liquidity, weekly money and banking tables) expose no stable
machine-readable file -- the pages are JS-rendered and the download links are session
bound -- so the EVDS API is used instead. It needs a free personal key passed as the
``key`` header; set ``EVDS_API_KEY`` or this source stays disabled.

Series (weekly, million USD):
  TP.AB.A01  gross foreign exchange reserves  -> metric ``gross_fx``
  TP.AB.A02  gold                             -> metric ``gold``
  TP.AB.A03  total reserves                   -> metric ``total``
EVDS returns the series as ``items[].TP_AB_A01`` etc. (dots replaced by underscores) and
the observation date as ``Tarih`` (``dd-mm-yyyy``). Values are multiplied by 1e6 so
``value_usd`` is in USD like the World Bank rows. Series ids could not be verified live
without a key; the mapping follows the EVDS catalogue and is easy to adjust in ``SERIES``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

EVDS_URL = "https://evds2.tcmb.gov.tr/service/evds/"
START_DATE = "01-01-2000"
SERIES = {
    "TP.AB.A01": "gross_fx",
    "TP.AB.A02": "gold",
    "TP.AB.A03": "total",
}
MILLION = Decimal(1_000_000)

COUNTRY_ISO3 = "TUR"
COUNTRY = "Turkiye"
SOURCE_NAME = "tcmb_evds"

_DATE_FORMATS = ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d")


def _parse_date(text: str) -> date:
    text = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised EVDS date {text!r}")


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None


def build_url(now: datetime) -> str:
    """EVDS encodes the query in the path, not as ``?k=v`` parameters."""
    series = "-".join(SERIES)
    end = now.strftime("%d-%m-%Y")
    return f"{EVDS_URL}series={series}&startDate={START_DATE}&endDate={end}&type=json"


def parse_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        try:
            period = _parse_date(str(item.get("Tarih", "")))
        except ValueError as exc:
            log.warning("tcmb reserves: skipping item %r: %s", item, exc)
            continue
        for series_id, metric in SERIES.items():
            value = _to_decimal(item.get(series_id.replace(".", "_")))
            if value is None:
                continue
            rows.append(
                {
                    "period_date": period,
                    "country_iso3": COUNTRY_ISO3,
                    "country": COUNTRY,
                    "metric": metric,
                    "value_usd": value * MILLION,
                    "source": SOURCE_NAME,
                }
            )
    return rows


def fetch(ctx: Ctx) -> Rows:
    key = ctx.env("EVDS_API_KEY")
    if not key:
        raise RuntimeError("EVDS_API_KEY is not set")
    resp = ctx.http.get(build_url(ctx.now), headers={"key": key})
    resp.raise_for_status()
    payload = resp.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("tcmb reserves: response has no 'items' list")
    rows = parse_items(items)
    if not rows:
        raise ValueError("tcmb reserves: no usable observations in response")
    log.info("tcmb reserves: %d rows", len(rows))
    return [("reserves", rows)]


SOURCE = Source(
    name="reserves_tcmb",
    interval=86400,
    fetch=fetch,
    backfill=None,
    requires_env=["EVDS_API_KEY"],
    tables=["reserves"],
    description="TCMB EVDS weekly Turkiye gross FX, gold and total reserves (USD)",
)

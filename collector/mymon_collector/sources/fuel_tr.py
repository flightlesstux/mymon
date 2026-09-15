"""Turkey pump prices from Petrol Ofisi's public province pages.

Candidates probed (2026-09): the Opet JSON API (``api.opet.com.tr/api/fuelprices/prices``)
never answers from this host (connect timeout) and opet.com.tr renders prices client-side
from that same API; shell.com.tr's price page is a 404. Petrol Ofisi serves a plain HTML
table per province at ``/akaryakit-fiyatlari/<slug>-akaryakit-fiyatlari`` with no auth, so
that is what we scrape.

Table shape (``<table class="table table-prices ...">``): a ``<thead>`` with ``<th>`` labels
(``Şehir``, ``V/Max Kurşunsuz 95``, ``V/Max Diesel``, ``Gazyağı``, ``Kalorifer Yakıtı``,
``Fuel Oil``, ``PO/gaz Otogaz``) and one ``<tr class="price-row" data-disctrict-name="...">``
per district whose cells hold ``<span class="with-tax">80.26</span>`` (TL/LT incl. VAT).
The first row is the province-level price (``ANKARA``, ``IZMIR``); Istanbul has
``ISTANBUL (AVRUPA)`` and ``ISTANBUL (ANADOLU)`` and we take Avrupa.

Only the pump fuels are kept (petrol95 / diesel / lpg); the page carries no timestamp, so
``period_date`` is today's date in Europe/Istanbul. Region is the province name.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE_URL = "https://www.petrolofisi.com.tr/akaryakit-fiyatlari/{slug}-akaryakit-fiyatlari"
SOURCE_NAME = "petrolofisi"
TZ = ZoneInfo("Europe/Istanbul")

# region label -> (url slug, preferred district-name substring or None for the first row)
PROVINCES: dict[str, tuple[str, str | None]] = {
    "Istanbul": ("istanbul", "AVRUPA"),
    "Ankara": ("ankara", None),
    "Izmir": ("izmir", None),
}

_TABLE_RE = re.compile(r"<table[^>]*table-prices[^>]*>(.*?)</table>", re.S | re.IGNORECASE)
_TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.S | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr([^>]*price-row[^>]*)>(.*?)</tr>", re.S | re.IGNORECASE)
_NAME_RE = re.compile(r'data-disctrict-name="([^"]*)"|data-district-name="([^"]*)"')
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.IGNORECASE)
_WITH_TAX_RE = re.compile(r'class="with-tax"[^>]*>\s*([0-9]+(?:[.,][0-9]+)?)', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


# --------------------------------------------------------------------------- helpers


def _text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", fragment)).strip()


def fuel_type_for(header: str) -> str | None:
    h = header.lower()
    if "otogaz" in h or "lpg" in h:
        return "lpg"
    if "diesel" in h or "dizel" in h or "motorin" in h:
        return "diesel"
    if "kurşunsuz" in h or "kursunsuz" in h or "benzin" in h or "95" in h:
        return "petrol95"
    return None


def _price(cell: str) -> float | None:
    m = _WITH_TAX_RE.search(cell)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_page(page_html: str, prefer: str | None) -> dict[str, float]:
    """``{fuel_type: price}`` for the province row of one Petrol Ofisi page."""
    m = _TABLE_RE.search(page_html)
    if not m:
        raise ValueError("no price table in page")
    table = m.group(1)
    headers = [_text(h) for h in _TH_RE.findall(table)]
    fuels = {idx: fuel_type_for(h) for idx, h in enumerate(headers)}
    if not any(fuels.values()):
        raise ValueError(f"no fuel columns in headers {headers}")

    rows = _ROW_RE.findall(table)
    if not rows:
        raise ValueError("price table has no rows")
    chosen: str | None = None
    if prefer:
        for attrs, body in rows:
            nm = _NAME_RE.search(attrs)
            name = (nm.group(1) or nm.group(2) or "") if nm else ""
            if prefer.upper() in name.upper():
                chosen = body
                break
        if chosen is None:
            log.warning("fuel_tr: no district matching %r, using first row", prefer)
    if chosen is None:
        chosen = rows[0][1]

    cells = _TD_RE.findall(chosen)
    out: dict[str, float] = {}
    for idx, cell in enumerate(cells):
        fuel = fuels.get(idx)
        if fuel is None or fuel in out:
            continue
        price = _price(cell)
        if price is None or price <= 0:
            log.warning("fuel_tr: unreadable %s cell %r", fuel, _text(cell)[:40])
            continue
        out[fuel] = price
    return out


# --------------------------------------------------------------------------- source


def fetch(ctx: Ctx) -> Rows:
    today: date = ctx.now.astimezone(TZ).date()
    rows: list[dict[str, Any]] = []
    failures = 0
    for region, (slug, prefer) in PROVINCES.items():
        url = BASE_URL.format(slug=slug)
        try:
            resp = ctx.http.get(url)
            resp.raise_for_status()
            prices = parse_page(resp.text, prefer)
        except Exception as exc:  # noqa: BLE001 - one province must not sink the others
            failures += 1
            log.warning("fuel_tr: %s failed: %s", region, exc)
            continue
        for fuel, price in prices.items():
            rows.append(
                {
                    "period_date": today,
                    "country_iso2": "TR",
                    "region": region,
                    "fuel_type": fuel,
                    "price": price,
                    "currency": "TRY",
                    "unit": "TRY/L",
                    "source": SOURCE_NAME,
                }
            )
    if failures == len(PROVINCES):
        raise RuntimeError("fuel_tr: every province page failed")
    return [("fuel_price", rows)]


SOURCE = Source(
    name="fuel_tr",
    interval=21600,
    fetch=fetch,
    backfill=None,
    tables=["fuel_price"],
    description="Turkey pump prices (Istanbul/Ankara/Izmir) scraped from Petrol Ofisi.",
)

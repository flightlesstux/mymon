"""FX rates: Frankfurter (ECB reference rates, USD base) and TCMB (Turkish central bank, TRY).

Frankfurter ``/v1/latest`` gives one USD-based snapshot per business day; TCMB ``today.xml``
gives the daily indicative selling rates for the foreign currencies quoted in TRY. Both are
stored in ``fx_rate`` keyed by ``(ts, base, quote, source)`` with ``ts`` at 00:00 UTC of the
publication date, so re-fetching the same day just overwrites the same rows.

Backfill pulls the full Frankfurter history (1999-01-04 onwards) in five-year chunks.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mymon_collector.source import Ctx, Rows, Source

log = logging.getLogger(__name__)

FRANKFURTER_V1 = "https://api.frankfurter.dev/v1"
FRANKFURTER_LEGACY = "https://api.frankfurter.app"
TCMB_TODAY = "https://www.tcmb.gov.tr/kurlar/today.xml"

FRANKFURTER_BASE = "USD"
FRANKFURTER_SYMBOLS = [
    "EUR", "GBP", "JPY", "TRY", "CHF", "CNY", "INR", "BRL",
    "MXN", "AUD", "CAD", "KRW", "SEK", "NOK", "PLN", "ZAR",
]
TCMB_CODES = {"USD", "EUR", "GBP", "CHF", "JPY", "SAR", "RUB", "CNY"}

FRANKFURTER_START = date(1999, 1, 4)
CHUNK_YEARS = 5


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _day_ts(day: str | date) -> datetime:
    if isinstance(day, str):
        day = date.fromisoformat(day)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


# --- Frankfurter --------------------------------------------------------------------------


def _frankfurter_get(ctx: Ctx, path: str) -> dict[str, Any]:
    params = {"base": FRANKFURTER_BASE, "symbols": ",".join(FRANKFURTER_SYMBOLS)}
    resp = ctx.http.get(f"{FRANKFURTER_V1}/{path}", params=params)
    if resp.status_code == 404:
        log.warning("frankfurter v1 returned 404 for %s, trying legacy host", path)
        resp = ctx.http.get(f"{FRANKFURTER_LEGACY}/{path}", params=params)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or "rates" not in data:
        raise ValueError(f"frankfurter: unexpected payload for {path}: {str(data)[:200]}")
    return data


def _frankfurter_rows(day: str, rates: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(rates, dict):
        log.warning("frankfurter: rates for %s is not a mapping, skipping", day)
        return rows
    try:
        ts = _day_ts(day)
    except ValueError:
        log.warning("frankfurter: bad date %r, skipping", day)
        return rows
    for quote, value in rates.items():
        rate = _dec(value)
        if rate is None:
            log.warning("frankfurter: bad rate for %s on %s: %r", quote, day, value)
            continue
        rows.append(
            {
                "ts": ts,
                "base": FRANKFURTER_BASE,
                "quote": str(quote).upper(),
                "rate": rate,
                "source": "frankfurter",
            }
        )
    return rows


def fetch_frankfurter(ctx: Ctx) -> list[dict[str, Any]]:
    data = _frankfurter_get(ctx, "latest")
    day = data.get("date")
    if not day:
        raise ValueError("frankfurter: latest response has no date")
    return _frankfurter_rows(str(day), data.get("rates"))


def _chunks(start: date, end: date) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        chunk_end = min(date(cur.year + CHUNK_YEARS - 1, 12, 31), end)
        out.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out


def backfill_frankfurter(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    today = ctx.now.date()
    for start, end in _chunks(FRANKFURTER_START, today):
        try:
            data = _frankfurter_get(ctx, f"{start.isoformat()}..{end.isoformat()}")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("frankfurter: chunk %s..%s failed: %s", start, end, exc)
            continue
        rates = data.get("rates")
        if not isinstance(rates, dict):
            log.warning("frankfurter: chunk %s..%s has no rates mapping", start, end)
            continue
        for day, day_rates in rates.items():
            rows.extend(_frankfurter_rows(str(day), day_rates))
    return rows


# --- TCMB ----------------------------------------------------------------------------------


def _tcmb_date(root: ET.Element) -> date:
    tarih = (root.get("Tarih") or "").strip()  # dd.mm.yyyy
    if tarih:
        try:
            return datetime.strptime(tarih, "%d.%m.%Y").date()
        except ValueError:
            pass
    us_date = (root.get("Date") or "").strip()  # mm/dd/yyyy
    if us_date:
        try:
            return datetime.strptime(us_date, "%m/%d/%Y").date()
        except ValueError:
            pass
    raise ValueError(f"tcmb: cannot parse document date (Tarih={tarih!r}, Date={us_date!r})")


def parse_tcmb(content: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"tcmb: invalid XML: {exc}") from exc
    ts = _day_ts(_tcmb_date(root))
    rows: list[dict[str, Any]] = []
    for cur in root.iter("Currency"):
        code = (cur.get("CurrencyCode") or cur.get("Kod") or "").strip().upper()
        if code not in TCMB_CODES:
            continue
        selling = _dec(cur.findtext("ForexSelling"))
        if selling is None:
            log.warning("tcmb: %s has no ForexSelling, skipping", code)
            continue
        unit = _dec(cur.findtext("Unit")) or Decimal(1)
        if unit <= 0:
            log.warning("tcmb: %s has bad Unit %r, skipping", code, cur.findtext("Unit"))
            continue
        rows.append(
            {"ts": ts, "base": code, "quote": "TRY", "rate": selling / unit, "source": "tcmb"}
        )
    if not rows:
        raise ValueError("tcmb: no usable Currency entries in document")
    return rows


def fetch_tcmb(ctx: Ctx) -> list[dict[str, Any]]:
    resp = ctx.http.get(TCMB_TODAY)
    resp.raise_for_status()
    return parse_tcmb(resp.content)


# --- Source ---------------------------------------------------------------------------------


def fetch(ctx: Ctx) -> Rows:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for name, fn in (("frankfurter", fetch_frankfurter), ("tcmb", fetch_tcmb)):
        try:
            rows.extend(fn(ctx))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("fx: %s fetch failed: %s", name, exc)
            failures.append(name)
    if len(failures) == 2:
        raise RuntimeError("fx: both frankfurter and tcmb failed")
    return [("fx_rate", rows)]


def backfill(ctx: Ctx) -> Rows:
    rows = backfill_frankfurter(ctx)
    try:
        rows.extend(fetch_tcmb(ctx))
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("fx: tcmb fetch during backfill failed: %s", exc)
    return [("fx_rate", rows)]


SOURCE = Source(
    name="fx",
    interval=3600,
    fetch=fetch,
    backfill=backfill,
    requires_env=[],
    tables=["fx_rate"],
    description="Daily FX rates: USD pairs from Frankfurter (ECB) and TRY pairs from TCMB.",
)

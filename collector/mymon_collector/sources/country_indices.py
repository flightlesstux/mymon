"""Daily closes for Germany/Italy/Spain/Greece/Turkey/France's main stock market index,
via Yahoo Finance's chart endpoint — same mechanism and no-key access as nl_us_stocks.py.

Lands in the existing ``stock_index`` table (day, symbol, close) rather than a new one —
that table already exists in the schema for exactly this purpose (originally meant for
commodities_stooq.py, which is disabled; this is the first source to actually populate
it) and needs no per-row company name, unlike nl_us_stock.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TABLE = "stock_index"
FETCH_TAIL = 10
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo ticker -> our symbol label. Confirmed live (2026-09). GD.AT (Greece) is a real
# limitation, not a query bug: Yahoo's chart API only has a single historical point for
# it, unlike every other ticker here which has years of daily closes — the "latest
# value" stat still works, there's just no trend to chart.
INDICES: dict[str, str] = {
    "^GDAXI": "DAX",       # Germany
    "^FCHI": "CAC40",      # France
    "^IBEX": "IBEX35",     # Spain
    "FTSEMIB.MI": "FTSEMIB",  # Italy
    "GD.AT": "ASE",        # Greece, Athens Composite
    "XU100.IS": "BIST100",  # Turkey
}


def _download(ctx: Ctx, ticker: str, tail: int | None) -> list[dict[str, Any]] | None:
    params: dict[str, Any] = {"interval": "1d"}
    if tail is None:
        params["period1"] = 0
        params["period2"] = int(ctx.now.replace(tzinfo=UTC).timestamp())
    else:
        params["range"] = f"{tail * 3}d"

    resp = ctx.http.get(CHART_URL.format(symbol=ticker), params=params, headers=HEADERS)
    if resp.status_code != 200:
        log.warning("country_indices: %s returned status %s", ticker, resp.status_code)
        return None
    body = resp.json().get("chart", {})
    result = body.get("result")
    if not result:
        log.warning("country_indices: %s -> %s", ticker, body.get("error"))
        return None

    r = result[0]
    timestamps = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    symbol = INDICES[ticker]
    rows: list[dict[str, Any]] = []
    for ts, close in zip(timestamps, closes, strict=False):
        if close is None:
            continue
        rows.append({
            "day": datetime.fromtimestamp(ts, tz=UTC).date(),
            "symbol": symbol,
            "close": close,
        })
    rows.sort(key=lambda row: row["day"])
    return rows[-tail:] if tail else rows


def _collect(ctx: Ctx, tail: int | None) -> Rows:
    rows: list[dict[str, Any]] = []
    for ticker in INDICES:
        series = _download(ctx, ticker, tail)
        if not series:
            continue
        rows.extend(series)
    return [(TABLE, rows)]


def fetch(ctx: Ctx) -> Rows:
    return _collect(ctx, FETCH_TAIL)


def backfill(ctx: Ctx) -> Rows:
    return _collect(ctx, None)


SOURCE = Source(
    name="country_indices",
    interval=3600,
    fetch=fetch,
    backfill=backfill,
    tables=[TABLE],
    description=(
        "Daily closes for Germany (DAX), France (CAC40), Spain (IBEX35), Italy "
        "(FTSE MIB), Greece (Athens Composite) and Turkey (BIST100) stock indices."
    ),
)

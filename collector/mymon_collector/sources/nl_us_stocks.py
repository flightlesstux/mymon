"""Daily closes for Dutch-domiciled companies listed on US exchanges.

Uses Yahoo Finance's unquoted chart endpoint (``query1.finance.yahoo.com/v8/finance/chart/
<symbol>``), no key required. ``period1=0&period2=now`` with ``interval=1d`` returns the
full daily history rather than the coarser bars Yahoo silently substitutes for
``range=max`` on old symbols.

Every symbol here is a company incorporated in the Netherlands (N.V.) whose primary or
sole listing is on NASDAQ/NYSE — not a UK/Dutch dual-listed name like Shell or Unilever
that has since redomiciled to the UK.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SOURCE_NAME = "yahoo_finance"
FETCH_TAIL = 10
HEADERS = {"User-Agent": "Mozilla/5.0"}

# symbol -> display name; all Netherlands N.V. companies on NASDAQ/NYSE
SYMBOLS: dict[str, str] = {
    "ASML": "ASML Holding",
    "ING": "ING Groep",
    "PHG": "Koninklijke Philips",
    "NXPI": "NXP Semiconductors",
    "STLA": "Stellantis",
    "LYB": "LyondellBasell Industries",
    "QGEN": "Qiagen",
}


def _download(ctx: Ctx, symbol: str, tail: int | None) -> list[dict[str, Any]] | None:
    params: dict[str, Any] = {"interval": "1d"}
    if tail is None:
        params["period1"] = 0
        params["period2"] = int(ctx.now.replace(tzinfo=UTC).timestamp())
    else:
        params["range"] = f"{tail * 3}d"  # pad for weekends/holidays, trimmed below

    resp = ctx.http.get(CHART_URL.format(symbol=symbol), params=params, headers=HEADERS)
    if resp.status_code != 200:
        log.warning("nl_us_stocks: %s returned status %s", symbol, resp.status_code)
        return None
    body = resp.json().get("chart", {})
    result = body.get("result")
    if not result:
        log.warning("nl_us_stocks: %s -> %s", symbol, body.get("error"))
        return None

    r = result[0]
    meta = r.get("meta", {})
    timestamps = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    rows: list[dict[str, Any]] = []
    for ts, close, volume in zip(timestamps, closes, volumes, strict=False):
        if close is None:
            continue
        rows.append({
            "day": datetime.fromtimestamp(ts, tz=UTC).date(),
            "symbol": symbol,
            "name": SYMBOLS[symbol],
            "close": close,
            "volume": volume,
            "currency": meta.get("currency"),
            "source": SOURCE_NAME,
        })
    rows.sort(key=lambda row: row["day"])
    return rows[-tail:] if tail else rows


def _collect(ctx: Ctx, tail: int | None) -> Rows:
    rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        series = _download(ctx, symbol, tail)
        if not series:
            continue
        rows.extend(series)
    return [("nl_us_stock", rows)]


def fetch(ctx: Ctx) -> Rows:
    return _collect(ctx, FETCH_TAIL)


def backfill(ctx: Ctx) -> Rows:
    return _collect(ctx, None)


SOURCE = Source(
    name="nl_us_stocks",
    interval=3600,
    fetch=fetch,
    backfill=backfill,
    tables=["nl_us_stock"],
    description=(
        "Daily closes for Dutch-domiciled (N.V.) companies listed on NASDAQ/NYSE: "
        "ASML, ING, Philips, NXP Semiconductors, Stellantis, LyondellBasell, Qiagen."
    ),
)

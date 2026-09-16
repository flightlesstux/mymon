"""Crypto spot prices from Binance (primary) with CoinGecko as fallback.

``fetch`` reads the Binance 24h ticker for a fixed symbol list every minute and stores one
``crypto_tick`` row per symbol at ``ctx.now`` truncated to the minute. Binance answers 451
from geo-blocked networks; in that case (or on any transport error) CoinGecko's
``simple/price`` endpoint is used instead, mapped through ``COINGECKO_IDS``.

``backfill`` pulls five years of daily klines per symbol from Binance, paging backwards with
``endTime``, into ``crypto_daily``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mymon_collector.source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BINANCE = "https://api.binance.com/api/v3"
COINGECKO_PRICE = "https://api.coingecko.com/api/v3/simple/price"

QUOTE = "USDT"
SYMBOLS = ["BTC", "ETH", "SOL", "PAXG", "BNB", "XRP", "ADA", "DOGE", "DOT", "AVAX", "LINK", "LTC"]
COINGECKO_IDS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "pax-gold": "PAXG",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "polkadot": "DOT",
    "avalanche-2": "AVAX",
    "chainlink": "LINK",
    "litecoin": "LTC",
}

BACKFILL_YEARS = 5
KLINE_LIMIT = 1000
MAX_PAGES_PER_SYMBOL = 10  # safety cap: 10 * 1000 daily candles is far beyond 5 years


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _strip_quote(symbol: str) -> str:
    symbol = symbol.upper()
    return symbol[: -len(QUOTE)] if symbol.endswith(QUOTE) else symbol


def _symbols_param() -> str:
    return json.dumps([f"{s}{QUOTE}" for s in SYMBOLS], separators=(",", ":"))


# --- fetch -----------------------------------------------------------------------------------


def _tick_ts(ctx: Ctx) -> datetime:
    return ctx.now.astimezone(UTC).replace(second=0, microsecond=0)


def parse_binance_ticker(payload: Any, ts: datetime) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"binance: unexpected ticker payload: {str(payload)[:200]}")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            log.warning("binance: skipping non-object ticker entry %r", item)
            continue
        symbol = item.get("symbol")
        price = _dec(item.get("lastPrice"))
        if not symbol or price is None:
            log.warning("binance: ticker entry missing symbol/lastPrice: %r", item)
            continue
        rows.append(
            {
                "ts": ts,
                "symbol": _strip_quote(str(symbol)),
                "price": price,
                "volume_24h": _dec(item.get("quoteVolume")),
                "change_24h_pct": _dec(item.get("priceChangePercent")),
            }
        )
    return rows


def parse_coingecko(payload: Any, ts: datetime) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError(f"coingecko: unexpected payload: {str(payload)[:200]}")
    rows: list[dict[str, Any]] = []
    for coin_id, symbol in COINGECKO_IDS.items():
        entry = payload.get(coin_id)
        if not isinstance(entry, dict):
            log.warning("coingecko: no entry for %s", coin_id)
            continue
        price = _dec(entry.get("usd"))
        if price is None:
            log.warning("coingecko: %s has no usd price: %r", coin_id, entry)
            continue
        rows.append(
            {
                "ts": ts,
                "symbol": symbol,
                "price": price,
                "volume_24h": _dec(entry.get("usd_24h_vol")),
                "change_24h_pct": _dec(entry.get("usd_24h_change")),
            }
        )
    return rows


def fetch_binance(ctx: Ctx, ts: datetime) -> list[dict[str, Any]]:
    resp = ctx.http.get(f"{BINANCE}/ticker/24hr", params={"symbols": _symbols_param()})
    resp.raise_for_status()
    return parse_binance_ticker(resp.json(), ts)


def fetch_coingecko(ctx: Ctx, ts: datetime) -> list[dict[str, Any]]:
    resp = ctx.http.get(
        COINGECKO_PRICE,
        params={
            "ids": ",".join(COINGECKO_IDS),
            "vs_currencies": "usd",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        },
    )
    resp.raise_for_status()
    return parse_coingecko(resp.json(), ts)


def fetch(ctx: Ctx) -> Rows:
    ts = _tick_ts(ctx)
    try:
        rows = fetch_binance(ctx, ts)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("crypto: binance ticker failed (%s), falling back to coingecko", exc)
        rows = fetch_coingecko(ctx, ts)
    if not rows:
        raise ValueError("crypto: no ticker rows parsed")
    return [("crypto_tick", rows)]


# --- backfill --------------------------------------------------------------------------------


def parse_klines(symbol: str, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError(f"binance: unexpected klines payload for {symbol}: {str(payload)[:200]}")
    rows: list[dict[str, Any]] = []
    for k in payload:
        if not isinstance(k, list) or len(k) < 6:
            log.warning("binance: malformed kline for %s: %r", symbol, k)
            continue
        try:
            open_ms = int(k[0])
        except (TypeError, ValueError):
            log.warning("binance: bad openTime for %s: %r", symbol, k[0])
            continue
        day = datetime.fromtimestamp(open_ms / 1000, tz=UTC).date()
        rows.append(
            {
                "day": day,
                "symbol": symbol,
                "open": _dec(k[1]),
                "high": _dec(k[2]),
                "low": _dec(k[3]),
                "close": _dec(k[4]),
                "volume": _dec(k[5]),
            }
        )
    return rows


def backfill_symbol(ctx: Ctx, symbol: str, since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    end_time: int | None = None
    for _ in range(MAX_PAGES_PER_SYMBOL):
        params: dict[str, Any] = {
            "symbol": f"{symbol}{QUOTE}",
            "interval": "1d",
            "limit": KLINE_LIMIT,
        }
        if end_time is not None:
            params["endTime"] = end_time
        resp = ctx.http.get(f"{BINANCE}/klines", params=params)
        resp.raise_for_status()
        payload = resp.json()
        page = parse_klines(symbol, payload)
        if not page:
            break
        rows.extend(page)
        first_open_ms = min(int(k[0]) for k in payload if isinstance(k, list) and k)
        if len(payload) < KLINE_LIMIT or first_open_ms <= int(since.timestamp() * 1000):
            break
        end_time = first_open_ms - 1
    return [r for r in rows if r["day"] >= since.date()]


def backfill(ctx: Ctx) -> Rows:
    since = ctx.now.astimezone(UTC) - timedelta(days=365 * BACKFILL_YEARS)
    rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        try:
            rows.extend(backfill_symbol(ctx, symbol, since))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("crypto: klines backfill for %s failed: %s", symbol, exc)
    if not rows:
        raise RuntimeError("crypto: backfill produced no rows")
    return [("crypto_daily", rows)]


SOURCE = Source(
    name="crypto",
    interval=60,
    fetch=fetch,
    backfill=backfill,
    requires_env=[],
    tables=["crypto_tick", "crypto_daily"],
    description="Crypto spot ticks (Binance, CoinGecko fallback) and 5y daily OHLCV backfill.",
)

"""Daily commodity futures and stock-index closes from Stooq CSV downloads.

``https://stooq.com/q/d/l/?s=<symbol>&i=d`` returns ``Date,Open,High,Low,Close,Volume`` for
the whole history of a symbol. Two non-CSV answers are handled:

- a JavaScript proof-of-work interstitial (``const c="...",d=4`` + ``POST /__verify``):
  we solve the SHA-256 puzzle in-process, post the nonce (the ``auth`` cookie is kept by
  ``ctx.http``) and retry the download once;
- plain-text bodies such as ``Exceeded the daily hits limit`` / ``Access denied`` or an
  empty body: logged as a warning and the symbol is skipped for that run.

Live status (probed 2026-09-15 from this host): the challenge solves fine and the quote
pages load, but every ``/q/d/l/`` download comes back as ``Access denied`` (indices, spot
metals) or an empty body (futures), from httpx and from a real browser alike, so the CSV
endpoint could not be verified and no symbol could be confirmed dead or alive. The module
is shipped complete but ``enabled: false`` in ``config/sources.yml``; re-enable once a
download works from the deployment host. ``XU100`` is tried as ``xu100`` then ``^xu100``.

``fetch`` keeps the last 10 rows per symbol, ``backfill`` the full history.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE_URL = "https://stooq.com/q/d/l/"
VERIFY_URL = "https://stooq.com/__verify"
SOURCE_NAME = "stooq"
FETCH_TAIL = 10
MAX_POW_ITERATIONS = 5_000_000

# stooq symbol -> (commodity key, unit)
COMMODITIES: dict[str, tuple[str, str]] = {
    "cb.f": ("brent", "USD/bbl"),
    "cl.f": ("wti", "USD/bbl"),
    "ng.f": ("natural_gas_us", "USD/MMBtu"),
    "xauusd": ("gold", "USD/oz"),
    "xagusd": ("silver", "USD/oz"),
    "hg.f": ("copper", "USD/lb"),
}
# index symbol -> candidate stooq symbols, first one that returns CSV wins
INDICES: dict[str, tuple[str, ...]] = {
    "SPX": ("^spx",),
    "DJI": ("^dji",),
    "NDQ": ("^ndq",),
    "DAX": ("^dax",),
    "UKX": ("^ukx",),
    "NKX": ("^nkx",),
    "XU100": ("xu100", "^xu100"),
}

_CHALLENGE_RE = re.compile(r'const c="([^"]+)",d=(\d+)')


# --------------------------------------------------------------------------- helpers


def solve_challenge(challenge: str, difficulty: int) -> int | None:
    """Smallest n with sha256(challenge + n) starting with ``difficulty`` zero hex digits."""
    prefix = "0" * difficulty
    for n in range(MAX_POW_ITERATIONS):
        if hashlib.sha256(f"{challenge}{n}".encode()).hexdigest().startswith(prefix):
            return n
    return None


def _pass_challenge(ctx: Ctx, body: str) -> bool:
    m = _CHALLENGE_RE.search(body)
    if not m:
        return False
    nonce = solve_challenge(m.group(1), int(m.group(2)))
    if nonce is None:
        log.warning("stooq: proof-of-work not solved within %d tries", MAX_POW_ITERATIONS)
        return False
    resp = ctx.http.post(VERIFY_URL, data={"c": m.group(1), "n": str(nonce)})
    ok = resp.status_code == 200
    log.info("stooq: challenge verify -> %s", resp.status_code)
    return ok


def parse_csv(text: str) -> list[tuple[date, float]]:
    """``[(day, close), ...]`` from a Stooq daily CSV; bad rows are skipped."""
    reader = csv.DictReader(io.StringIO(text))
    out: list[tuple[date, float]] = []
    bad = 0
    for rec in reader:
        try:
            day = date.fromisoformat((rec.get("Date") or "").strip())
            close = float((rec.get("Close") or "").strip())
        except ValueError:
            bad += 1
            continue
        out.append((day, close))
    if bad:
        log.warning("stooq: skipped %d unparsable rows", bad)
    return out


def _is_csv(text: str) -> bool:
    return text.lstrip().lower().startswith("date,")


def _download(ctx: Ctx, symbol: str) -> list[tuple[date, float]] | None:
    resp = ctx.http.get(BASE_URL, params={"s": symbol, "i": "d"})
    text = resp.text
    if not _is_csv(text) and _pass_challenge(ctx, text):
        resp = ctx.http.get(BASE_URL, params={"s": symbol, "i": "d"})
        text = resp.text
    if resp.status_code != 200 or not _is_csv(text):
        log.warning(
            "stooq: %s returned non-CSV (status %s): %r", symbol, resp.status_code, text[:80]
        )
        return None
    return parse_csv(text)


def _collect(ctx: Ctx, tail: int | None) -> Rows:
    commodity_rows: list[dict[str, Any]] = []
    for symbol, (commodity, unit) in COMMODITIES.items():
        series = _download(ctx, symbol)
        if not series:
            continue
        for day, close in series[-tail:] if tail else series:
            commodity_rows.append(
                {
                    "period_date": day,
                    "commodity": commodity,
                    "price": close,
                    "unit": unit,
                    "source": SOURCE_NAME,
                }
            )

    index_rows: list[dict[str, Any]] = []
    for name, candidates in INDICES.items():
        series = None
        for symbol in candidates:
            series = _download(ctx, symbol)
            if series:
                break
        if not series:
            log.warning("stooq: no data for index %s (%s)", name, ", ".join(candidates))
            continue
        for day, close in series[-tail:] if tail else series:
            index_rows.append({"day": day, "symbol": name, "close": close})

    return [("commodity_price", commodity_rows), ("stock_index", index_rows)]


# --------------------------------------------------------------------------- source


def fetch(ctx: Ctx) -> Rows:
    return _collect(ctx, FETCH_TAIL)


def backfill(ctx: Ctx) -> Rows:
    return _collect(ctx, None)


SOURCE = Source(
    name="commodities_stooq",
    interval=3600,
    fetch=fetch,
    backfill=backfill,
    tables=["commodity_price", "stock_index"],
    description="Stooq daily closes: oil, gas, metals futures/spot and major stock indices.",
)

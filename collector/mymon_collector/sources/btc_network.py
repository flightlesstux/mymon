"""Bitcoin network stats from mempool.space.

fetch (one row, ``ts`` = ctx.now truncated to the minute):
  ``/v1/fees/recommended``      -> fastestFee, halfHourFee, hourFee, economyFee (sat/vB)
  ``/blocks/tip/height``        -> plain integer body
  ``/mempool``                  -> count, vsize
  ``/v1/mining/hashrate/3d``    -> currentHashrate (H/s), currentDifficulty
backfill: ``/v1/mining/hashrate/1y`` -> one row per ``hashrates[]`` point (daily average),
with ``difficulty`` filled from the most recent adjustment at or before that point.

Each endpoint is fetched independently; if one fails the row still carries the others.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE = "https://mempool.space/api"
FEES_URL = f"{BASE}/v1/fees/recommended"
TIP_URL = f"{BASE}/blocks/tip/height"
MEMPOOL_URL = f"{BASE}/mempool"
HASHRATE_3D_URL = f"{BASE}/v1/mining/hashrate/3d"
HASHRATE_1Y_URL = f"{BASE}/v1/mining/hashrate/1y"
_EH = 1e18

COLUMNS = (
    "ts",
    "block_height",
    "hashrate_ehs",
    "difficulty",
    "fee_fast",
    "fee_half_hour",
    "fee_hour",
    "fee_economy",
    "mempool_tx_count",
    "mempool_vsize",
)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    num = _num(value)
    return None if num is None else int(num)


def _get_json(ctx: Ctx, url: str) -> Any:
    try:
        resp = ctx.http.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - one endpoint failing must not sink the row
        log.warning("mempool.space %s failed: %s", url, exc)
        return None


def _get_text(ctx: Ctx, url: str) -> str | None:
    try:
        resp = ctx.http.get(url)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:  # noqa: BLE001
        log.warning("mempool.space %s failed: %s", url, exc)
        return None


def _empty_row(ts: datetime) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(COLUMNS)
    row["ts"] = ts
    return row


def fetch(ctx: Ctx) -> Rows:
    row = _empty_row(ctx.now.astimezone(UTC).replace(second=0, microsecond=0))

    fees = _get_json(ctx, FEES_URL)
    if isinstance(fees, dict):
        row["fee_fast"] = _num(fees.get("fastestFee"))
        row["fee_half_hour"] = _num(fees.get("halfHourFee"))
        row["fee_hour"] = _num(fees.get("hourFee"))
        row["fee_economy"] = _num(fees.get("economyFee"))

    tip = _get_text(ctx, TIP_URL)
    if tip is not None:
        row["block_height"] = _int(tip.strip())

    mempool = _get_json(ctx, MEMPOOL_URL)
    if isinstance(mempool, dict):
        row["mempool_tx_count"] = _int(mempool.get("count"))
        row["mempool_vsize"] = _int(mempool.get("vsize"))

    mining = _get_json(ctx, HASHRATE_3D_URL)
    if isinstance(mining, dict):
        hashrate = _num(mining.get("currentHashrate"))
        row["hashrate_ehs"] = None if hashrate is None else hashrate / _EH
        row["difficulty"] = _num(mining.get("currentDifficulty"))

    if all(row[c] is None for c in COLUMNS if c != "ts"):
        raise RuntimeError("all mempool.space endpoints failed")
    return [("btc_network", [row])]


def parse_history(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("hashrates"), list):
        raise ValueError("mempool.space hashrate history has no 'hashrates' list")

    adjustments: list[tuple[int, float]] = []
    for item in payload.get("difficulty") or []:
        t, d = _int((item or {}).get("time")), _num((item or {}).get("difficulty"))
        if t is not None and d is not None:
            adjustments.append((t, d))
    adjustments.sort()

    rows: list[dict[str, Any]] = []
    for point in payload["hashrates"]:
        t = _int((point or {}).get("timestamp"))
        hashrate = _num((point or {}).get("avgHashrate"))
        if t is None or hashrate is None:
            log.warning("skipping hashrate point without timestamp/avgHashrate: %r", point)
            continue
        difficulty = None
        for adj_t, adj_d in adjustments:
            if adj_t <= t:
                difficulty = adj_d
            else:
                break
        row = _empty_row(datetime.fromtimestamp(t, tz=UTC))
        row["hashrate_ehs"] = hashrate / _EH
        row["difficulty"] = difficulty
        rows.append(row)
    return rows


def backfill(ctx: Ctx) -> Rows:
    resp = ctx.http.get(HASHRATE_1Y_URL)
    resp.raise_for_status()
    rows = parse_history(resp.json())
    log.info("btc_network backfill loaded %d daily hashrate points", len(rows))
    return [("btc_network", rows)]


SOURCE = Source(
    name="btc_network",
    interval=120,
    fetch=fetch,
    backfill=backfill,
    tables=["btc_network"],
    description="Bitcoin fees, tip height, mempool size, hashrate and difficulty (mempool.space)",
)

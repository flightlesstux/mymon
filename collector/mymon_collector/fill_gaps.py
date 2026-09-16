"""One-off runner: fills the gap between 2026-01-01 and this collector's first run, for the
sources where a free historical API actually exists (see historical_fill.py's docstrings for
why the rest can't be done). Idempotent — every row upserts on its table's primary key, so
running this twice just re-writes the same rows.

Usage (inside the collector container, which already has network access to postgres and
every dependency installed — see `make fill-gaps`):

    python -m mymon_collector.fill_gaps
    python -m mymon_collector.fill_gaps --start 2026-01-01 --end 2026-09-16
    python -m mymon_collector.fill_gaps --only fx,space_weather
    python -m mymon_collector.fill_gaps --only weather --start 2025-01-01 \\
        --cities "Rotterdam,Utrecht"
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime

from . import db, historical_fill, registry
from .http import make_client
from .source import Ctx

log = logging.getLogger("mymon.fill_gaps")

JOBS: dict[str, tuple[str, Callable[[Ctx, date, date], list[dict]]]] = {
    "fx": ("fx_rate", historical_fill.tcmb_daily),
    "space_weather": ("space_weather", historical_fill.kp_history),
    "weather": ("weather_current", historical_fill.weather_hourly),
    "fuel_tr": ("fuel_price", historical_fill.fuel_tr_wayback),
}


def _upsert_chunked(conn, table: str, rows: list[dict], chunk_size: int = 5000) -> int:
    total = 0
    for i in range(0, len(rows), chunk_size):
        total += db.upsert(conn, table, rows[i : i + chunk_size])
        conn.commit()
    return total


def main() -> int:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--only", type=str, default=None,
                        help="comma-separated subset of: " + ",".join(JOBS))
    parser.add_argument("--cities", type=str, default=None,
                        help="comma-separated city names to restrict the weather job to "
                             "(default: every configured city)")
    args = parser.parse_args()
    end = args.end or datetime.now(UTC).date()
    names = [n.strip() for n in args.only.split(",")] if args.only else list(JOBS)

    cfg = registry.load_ctx_config()
    if args.cities:
        wanted = {c.strip() for c in args.cities.split(",")}
        cfg = {**cfg, "cities": [c for c in cfg["cities"] if c["name"] in wanted]}
        missing = wanted - {c["name"] for c in cfg["cities"]}
        if missing:
            log.warning("--cities: not found in config, ignored: %s", ", ".join(sorted(missing)))
    ok, failed = [], []
    with make_client(timeout=60) as http, db.pool().connection() as conn:
        ctx = Ctx(http=http, cfg=cfg, now=datetime.now(UTC))
        for name in names:
            if name not in JOBS:
                log.error("unknown job %r, skipping (known: %s)", name, ", ".join(JOBS))
                failed.append(name)
                continue
            table, fn = JOBS[name]
            log.info("=== %s -> %s: %s to %s ===", name, table, args.start, end)
            try:
                rows = fn(ctx, args.start, end)
            except Exception:
                log.exception("%s: fetch failed", name)
                failed.append(name)
                continue
            if not rows:
                log.warning("%s: produced no rows", name)
                failed.append(name)
                continue
            n = _upsert_chunked(conn, table, rows)
            log.info("%s: upserted %d rows into %s", name, n, table)
            ok.append(name)

    log.info("done. ok=%s failed=%s", ok, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

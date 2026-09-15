"""APScheduler wiring: one interval job per source, backfill on first run, daily retention."""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, retention
from .http import make_client
from .source import Ctx, Rows, Source

log = logging.getLogger(__name__)


def _write(conn, result: Rows) -> int:
    total = 0
    for table, rows in result:
        total += db.upsert(conn, table, rows)
    return total


def run_source(source: Source, cfg: dict) -> None:
    started = datetime.now(UTC)
    rows_written = 0
    error: str | None = None
    ok = True
    try:
        with db.pool().connection() as conn, make_client() as http:
            ctx = Ctx(http=http, cfg=cfg, now=started)
            if source.backfill and source.tables and any(
                db.table_empty(conn, t) for t in source.tables
            ):
                log.info("[%s] backfilling", source.name)
                rows_written += _write(conn, source.backfill(ctx))
                conn.commit()
            rows_written += _write(conn, source.fetch(ctx))
            conn.commit()
    except Exception as exc:  # noqa: BLE001 - a bad source must never kill the scheduler
        ok = False
        error = f"{type(exc).__name__}: {exc}"
        log.error("[%s] failed: %s\n%s", source.name, error, traceback.format_exc())
    finished = datetime.now(UTC)
    log.info("[%s] ok=%s rows=%d in %.1fs", source.name, ok, rows_written,
             (finished - started).total_seconds())
    try:
        with db.pool().connection() as conn:
            db.record_run(conn, source.name, started, finished, ok, rows_written, error)
            conn.commit()
    except Exception:  # noqa: BLE001
        log.exception("[%s] could not record run", source.name)


def build(sources: list[Source], cfg: dict) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC")
    stagger = 0
    for src in sources:
        sched.add_job(
            run_source,
            "interval",
            seconds=src.interval,
            args=[src, cfg],
            id=src.name,
            name=src.name,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=max(60, src.interval),
            jitter=min(10, max(1, src.interval // 10)),
            next_run_time=datetime.now(UTC) + timedelta(seconds=stagger),
        )
        stagger += 5
    sched.add_job(
        retention.run,
        CronTrigger(hour=3, minute=0),
        id="retention",
        name="retention",
        max_instances=1,
    )
    return sched

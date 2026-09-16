"""Daily cleanup of high-frequency tables. Slow macro tables are kept forever."""

from __future__ import annotations

import logging

from psycopg import sql

from . import db

log = logging.getLogger(__name__)

# table -> (timestamp column, keep interval)
#
# weather_current and space_weather used to be here (730d / 365d) but both are now backfilled
# with decades of history for the dashboards that chart them long-range (NL: Weather, Earth &
# Space's Kp panel) — a nightly delete would have undone that backfill within a year. Only
# genuinely-high-frequency, dashboard-doesn't-need-the-deep-past tables stay policed.
POLICY: dict[str, tuple[str, str]] = {
    "crypto_tick": ("ts", "90 days"),
    "iss_position": ("ts", "7 days"),
    "aircraft_state": ("ts", "2 days"),
    "btc_network": ("ts", "180 days"),
    "energy_grid": ("ts", "30 days"),
    "bike_network": ("ts", "14 days"),
    "natural_event": ("event_date", "45 days"),
    "astronaut": ("ts", "3 days"),
    "space_launch": ("net", "400 days"),
    "collector_run": ("started_at", "30 days"),
}


def delete_statement(table: str, column: str, keep: str) -> sql.Composed:
    return sql.SQL("DELETE FROM {t} WHERE {c} < now() - interval {k}").format(
        t=sql.Identifier(table), c=sql.Identifier(column), k=sql.Literal(keep)
    )


def run() -> None:
    with db.pool().connection() as conn:
        for table, (column, keep) in POLICY.items():
            with conn.cursor() as cur:
                cur.execute(delete_statement(table, column, keep))
                log.info("retention: %s removed %d rows older than %s", table, cur.rowcount, keep)
        conn.commit()

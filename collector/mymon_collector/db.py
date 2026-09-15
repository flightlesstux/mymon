"""PostgreSQL access: connection pool, generic primary-key upsert, run bookkeeping."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

_pk_cache: dict[str, list[str]] = {}
_pool: ConnectionPool | None = None


def dsn_from_env() -> str:
    return (
        f"host={os.environ.get('PGHOST', 'localhost')} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'mymon')} "
        f"user={os.environ.get('POSTGRES_USER', 'mymon')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', '')}"
    )


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(dsn_from_env(), min_size=1, max_size=4, open=True)
    return _pool


def primary_key(conn: psycopg.Connection, table: str) -> list[str]:
    if table in _pk_cache:
        return _pk_cache[table]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
            """,
            (table,),
        )
        cols = [r[0] for r in cur.fetchall()]
    if not cols:
        raise ValueError(f"table {table!r} has no primary key (or does not exist)")
    _pk_cache[table] = cols
    return cols


def build_upsert(table: str, columns: list[str], pk: list[str]) -> sql.Composed:
    """Build ``INSERT ... ON CONFLICT (pk) DO UPDATE`` for the given column order."""
    non_pk = [c for c in columns if c not in pk]
    insert = sql.SQL("INSERT INTO {t} ({cols}) VALUES ({vals})").format(
        t=sql.Identifier(table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        vals=sql.SQL(", ").join(sql.Placeholder(c) for c in columns),
    )
    conflict = sql.SQL(" ON CONFLICT ({pk})").format(
        pk=sql.SQL(", ").join(sql.Identifier(c) for c in pk)
    )
    if non_pk:
        action = sql.SQL(" DO UPDATE SET {sets}").format(
            sets=sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in non_pk
            )
        )
    else:
        action = sql.SQL(" DO NOTHING")
    return insert + conflict + action


def upsert(conn: psycopg.Connection, table: str, rows: list[dict[str, Any]]) -> int:
    """Upsert rows. All rows must share the same key set. Returns row count."""
    if not rows:
        return 0
    pk = primary_key(conn, table)
    columns = list(rows[0].keys())
    missing = [c for c in pk if c not in columns]
    if missing:
        raise ValueError(f"{table}: rows missing primary key columns {missing}")
    stmt = build_upsert(table, columns, pk)
    with conn.cursor() as cur:
        cur.executemany(stmt, rows)
    return len(rows)


def table_empty(conn: psycopg.Connection, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT 1 FROM {t} LIMIT 1").format(t=sql.Identifier(table)))
        return cur.fetchone() is None


def record_run(
    conn: psycopg.Connection,
    source: str,
    started: datetime,
    finished: datetime,
    ok: bool,
    rows: int,
    error: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO collector_run (source, started_at, finished_at, ok, rows, error)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (source, started, finished, ok, rows, error),
        )

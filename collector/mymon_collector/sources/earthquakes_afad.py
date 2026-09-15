"""AFAD (Turkey) earthquake catalogue.

Endpoint: ``https://deprem.afad.gov.tr/apiv2/event/filter`` (302-redirects to
``servisnet.afad.gov.tr/apigateway/deprem/...``; the shared client follows redirects).
Query params ``start``/``end`` use ``YYYY-MM-DD HH:MM:SS`` (UTC); the space is sent as ``+``
by httpx's form encoding and the API accepts it. Response is a JSON array of objects whose
numeric fields are strings: ``eventID, date (ISO, UTC), latitude, longitude, depth, magnitude,
location``.

fetch: last 24h, ``minmag=1.0``. backfill: last 365 days, ``minmag=3.0``, in ~30-day chunks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

FILTER_URL = "https://deprem.afad.gov.tr/apiv2/event/filter"
SOURCE_TAG = "afad"
_TS_FMT = "%Y-%m-%d %H:%M:%S"
_CHUNK = timedelta(days=30)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    ts = datetime.fromisoformat(str(value))
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def _event_to_row(ev: dict[str, Any]) -> dict[str, Any] | None:
    ev_id = ev.get("eventID") or ev.get("eventId") or ev.get("id")
    ts = _parse_date(ev.get("date"))
    lat, lon = _num(ev.get("latitude")), _num(ev.get("longitude"))
    if not ev_id or ts is None or lat is None or lon is None:
        return None
    return {
        "id": f"{SOURCE_TAG}:{ev_id}",
        "ts": ts,
        "lat": lat,
        "lon": lon,
        "depth_km": _num(ev.get("depth")),
        "mag": _num(ev.get("magnitude")),
        "place": ev.get("location"),
        "source": SOURCE_TAG,
    }


def parse_events(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("AFAD response is not a JSON array")
    rows: list[dict[str, Any]] = []
    for ev in payload:
        if not isinstance(ev, dict):
            log.warning("skipping non-object AFAD record: %r", ev)
            continue
        try:
            row = _event_to_row(ev)
        except (TypeError, ValueError) as exc:
            log.warning("skipping malformed AFAD event %r: %s", ev.get("eventID"), exc)
            continue
        if row is None:
            log.warning("skipping AFAD event without id/date/coords: %r", ev.get("eventID"))
            continue
        rows.append(row)
    return rows


def _query(ctx: Ctx, start: datetime, end: datetime, minmag: str) -> list[dict[str, Any]]:
    resp = ctx.http.get(
        FILTER_URL,
        params={
            "start": start.astimezone(UTC).strftime(_TS_FMT),
            "end": end.astimezone(UTC).strftime(_TS_FMT),
            "minmag": minmag,
            "orderby": "timedesc",
        },
    )
    resp.raise_for_status()
    return parse_events(resp.json())


def fetch(ctx: Ctx) -> Rows:
    return [("earthquake", _query(ctx, ctx.now - timedelta(hours=24), ctx.now, "1.0"))]


def backfill(ctx: Ctx) -> Rows:
    rows: list[dict[str, Any]] = []
    start = ctx.now - timedelta(days=365)
    while start < ctx.now:
        end = min(start + _CHUNK, ctx.now)
        chunk = _query(ctx, start, end, "3.0")
        log.info("afad backfill %s..%s: %d events", start.date(), end.date(), len(chunk))
        rows.extend(chunk)
        start = end
    return [("earthquake", rows)]


SOURCE = Source(
    name="earthquakes_afad",
    interval=600,
    fetch=fetch,
    backfill=backfill,
    tables=["earthquake"],
    description="AFAD Turkey earthquake catalogue (M1.0+ last 24h; M3.0+ one-year backfill)",
)

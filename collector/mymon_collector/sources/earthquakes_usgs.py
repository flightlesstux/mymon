"""USGS earthquake feed (GeoJSON).

fetch: the ``all_day`` summary feed (every event of the last 24h, any magnitude).
backfill: FDSN event query for the last year with ``minmagnitude=4.5``.
Both share the same GeoJSON ``features`` shape: ``id``, ``properties.time`` (ms epoch),
``properties.mag``, ``properties.place``, ``geometry.coordinates = [lon, lat, depth_km]``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
SOURCE_TAG = "usgs"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _feature_to_row(feature: dict[str, Any]) -> dict[str, Any] | None:
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    ev_id = feature.get("id")
    if not ev_id or len(coords) < 2:
        return None
    time_ms = props.get("time")
    if time_ms is None:
        return None
    lon, lat = _num(coords[0]), _num(coords[1])
    if lat is None or lon is None:
        return None
    return {
        "id": f"{SOURCE_TAG}:{ev_id}",
        "ts": datetime.fromtimestamp(int(time_ms) / 1000, tz=UTC),
        "lat": lat,
        "lon": lon,
        "depth_km": _num(coords[2]) if len(coords) > 2 else None,
        "mag": _num(props.get("mag")),
        "place": props.get("place"),
        "source": SOURCE_TAG,
    }


def parse_geojson(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ValueError("USGS response has no 'features' list")
    rows: list[dict[str, Any]] = []
    for feature in payload["features"]:
        try:
            row = _feature_to_row(feature)
        except (TypeError, ValueError, OverflowError) as exc:
            log.warning("skipping malformed USGS feature %r: %s", feature.get("id"), exc)
            continue
        if row is None:
            log.warning("skipping USGS feature without id/time/coords: %r", feature.get("id"))
            continue
        rows.append(row)
    return rows


def fetch(ctx: Ctx) -> Rows:
    resp = ctx.http.get(FEED_URL)
    resp.raise_for_status()
    return [("earthquake", parse_geojson(resp.json()))]


def backfill(ctx: Ctx) -> Rows:
    start = (ctx.now - timedelta(days=365)).date().isoformat()
    resp = ctx.http.get(
        QUERY_URL,
        params={
            "format": "geojson",
            "starttime": start,
            "minmagnitude": "4.5",
            "orderby": "time",
            "limit": "20000",
        },
    )
    resp.raise_for_status()
    rows = parse_geojson(resp.json())
    log.info("usgs backfill loaded %d events since %s", len(rows), start)
    return [("earthquake", rows)]


SOURCE = Source(
    name="earthquakes_usgs",
    interval=300,
    fetch=fetch,
    backfill=backfill,
    tables=["earthquake"],
    description="USGS global earthquake feed (all magnitudes, last 24h; M4.5+ one-year backfill)",
)

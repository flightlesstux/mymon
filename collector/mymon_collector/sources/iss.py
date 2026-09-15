"""ISS position from wheretheiss.at (NORAD 25544).

Response: ``{timestamp (epoch s), latitude, longitude, altitude (km), velocity (km/h), ...}``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

URL = "https://api.wheretheiss.at/v1/satellites/25544"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_position(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("wheretheiss response is not an object")
    ts_raw = payload.get("timestamp")
    lat, lon = _num(payload.get("latitude")), _num(payload.get("longitude"))
    if ts_raw is None or lat is None or lon is None:
        raise ValueError(f"wheretheiss response missing timestamp/lat/lon: {payload!r}")
    if payload.get("units") not in (None, "kilometers"):
        log.warning("wheretheiss units=%r, expected kilometers", payload.get("units"))
    return {
        "ts": datetime.fromtimestamp(int(ts_raw), tz=UTC),
        "lat": lat,
        "lon": lon,
        "altitude_km": _num(payload.get("altitude")),
        "velocity_kmh": _num(payload.get("velocity")),
    }


def fetch(ctx: Ctx) -> Rows:
    resp = ctx.http.get(URL)
    resp.raise_for_status()
    return [("iss_position", [parse_position(resp.json())])]


SOURCE = Source(
    name="iss",
    interval=60,
    fetch=fetch,
    backfill=None,
    tables=["iss_position"],
    description="International Space Station position, altitude and velocity",
)

"""NOAA SWPC space weather: planetary Kp plus solar wind speed/density and IMF Bz.

Kp: ``products/noaa-planetary-k-index.json``. Historically an array of arrays with a header
row ``["time_tag","Kp","a_running","station_count"]``; as of the live probe it is an array of
objects with the same keys. Both shapes are parsed. Rows are keyed by the 3-hour Kp
``time_tag`` (UTC); every entry from the last 24h is emitted.

Solar wind: the ``products/solar-wind/plasma-5-minute.json`` / ``mag-5-minute.json`` files
return 404 (probed live), so the real-time 1-minute feeds are used instead:
``json/rtsw/rtsw_wind_1m.json`` (``proton_speed`` km/s, ``proton_density`` p/cc) and
``json/rtsw/rtsw_mag_1m.json`` (``bz_gsm`` nT). Both are newest-first and contain one entry
per spacecraft; the first entry with ``active: true`` (or simply the first) is taken. The
latest Kp row carries these wind fields; older rows have them as None.

No backfill: the Kp file itself covers about a week.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
WIND_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
MAG_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def _as_objects(payload: Any) -> list[dict[str, Any]]:
    """Normalise SWPC's two JSON layouts (header-row arrays or plain objects) to dicts."""
    if not isinstance(payload, list):
        raise ValueError("SWPC response is not a JSON array")
    if not payload:
        return []
    if isinstance(payload[0], dict):
        return [x for x in payload if isinstance(x, dict)]
    header = payload[0]
    if not isinstance(header, list):
        raise ValueError("SWPC response has neither objects nor a header row")
    out: list[dict[str, Any]] = []
    for row in payload[1:]:
        if isinstance(row, list) and len(row) == len(header):
            out.append(dict(zip(header, row, strict=True)))
        else:
            log.warning("skipping SWPC row with unexpected width: %r", row)
    return out


def parse_kp(payload: Any, since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in _as_objects(payload):
        try:
            ts = _parse_ts(entry.get("time_tag"))
        except ValueError as exc:
            log.warning("skipping Kp entry with bad time_tag %r: %s", entry.get("time_tag"), exc)
            continue
        if ts is None or ts < since:
            continue
        kp = _num(entry.get("Kp", entry.get("kp", entry.get("estimated_kp"))))
        rows.append(
            {"ts": ts, "kp": kp, "solar_wind_speed": None, "solar_wind_density": None, "bz": None}
        )
    rows.sort(key=lambda r: r["ts"])
    return rows


def _latest(payload: Any) -> dict[str, Any] | None:
    entries = _as_objects(payload)
    if not entries:
        return None
    for entry in entries:
        if entry.get("active") is True:
            return entry
    return entries[0]


def _fetch_latest(ctx: Ctx, url: str) -> dict[str, Any] | None:
    try:
        resp = ctx.http.get(url)
        resp.raise_for_status()
        return _latest(resp.json())
    except Exception as exc:  # noqa: BLE001 - wind data is optional
        log.warning("SWPC %s unavailable: %s", url, exc)
        return None


def fetch(ctx: Ctx) -> Rows:
    resp = ctx.http.get(KP_URL)
    resp.raise_for_status()
    rows = parse_kp(resp.json(), ctx.now - timedelta(hours=24))
    if not rows:
        raise RuntimeError("SWPC Kp file has no entries in the last 24h")

    wind = _fetch_latest(ctx, WIND_URL)
    mag = _fetch_latest(ctx, MAG_URL)
    latest = rows[-1]
    if wind:
        latest["solar_wind_speed"] = _num(wind.get("proton_speed", wind.get("speed")))
        latest["solar_wind_density"] = _num(wind.get("proton_density", wind.get("density")))
    if mag:
        latest["bz"] = _num(mag.get("bz_gsm"))
    return [("space_weather", rows)]


SOURCE = Source(
    name="space_weather",
    interval=600,
    fetch=fetch,
    backfill=None,
    tables=["space_weather"],
    description="NOAA SWPC planetary Kp index with latest solar wind speed, density and Bz",
)

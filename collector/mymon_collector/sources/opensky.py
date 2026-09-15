"""OpenSky Network source: live aircraft state vectors over Europe, the Middle East and Türkiye.

Auth is OAuth2 client credentials. ``POST`` form
``grant_type=client_credentials&client_id=..&client_secret=..`` to::

    https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token

-> ``{"access_token": "...", "expires_in": 1800, ...}``. The token is cached in this module and
refreshed a minute before it expires (or immediately after a 401).

Data: ``GET https://opensky-network.org/api/states/all?lamin=34&lomin=-12&lamax=62&lomax=45``
with ``Authorization: Bearer <token>`` -> ``{"time": <epoch>, "states": [[...], ...]}`` where
each state vector is positional::

    0 icao24  1 callsign  2 origin_country  3 time_position  4 last_contact  5 longitude
    6 latitude  7 baro_altitude  8 on_ground  9 velocity (m/s)  10 true_track  11 vertical_rate
    12 sensors  13 geo_altitude  14 squawk  15 spi  16 position_source  [17 category]

``states`` is ``null`` when nothing matched. Rows use ``ts = time`` (one snapshot per poll);
vectors without a position are skipped; ``alt_m`` is the barometric altitude, falling back to
the geometric one when that is missing; ``velocity`` stays in m/s.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
STATES_URL = "https://opensky-network.org/api/states/all"
BBOX = {"lamin": 34, "lomin": -12, "lamax": 62, "lomax": 45}
TOKEN_SAFETY_S = 60
DEFAULT_TOKEN_TTL_S = 1800

_token: tuple[str, float] | None = None  # (access_token, expires_at epoch)


# --------------------------------------------------------------------------- helpers


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reset_token_cache() -> None:
    global _token
    _token = None


def _get_token(ctx: Ctx, *, force: bool = False) -> str:
    global _token
    if not force and _token is not None and _token[1] > _time.time():
        return _token[0]
    client_id = ctx.env("OPENSKY_CLIENT_ID")
    client_secret = ctx.env("OPENSKY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("opensky: OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET not set")
    resp = ctx.http.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError("opensky: token response has no access_token")
    ttl = _num(payload.get("expires_in")) or DEFAULT_TOKEN_TTL_S
    _token = (token, _time.time() + max(ttl - TOKEN_SAFETY_S, 30))
    return token


def _states(ctx: Ctx) -> dict[str, Any]:
    token = _get_token(ctx)
    resp = ctx.http.get(STATES_URL, params=BBOX, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 401:
        log.info("opensky: token rejected, refreshing")
        token = _get_token(ctx, force=True)
        resp = ctx.http.get(STATES_URL, params=BBOX, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("opensky: unexpected states payload type")
    return payload


def _row(ts: datetime, vec: Any) -> dict[str, Any] | None:
    if not isinstance(vec, list | tuple) or len(vec) < 11:
        return None
    icao24 = vec[0]
    if not isinstance(icao24, str) or not icao24:
        return None
    lat, lon = _num(vec[6]), _num(vec[5])
    if lat is None or lon is None:
        return None
    callsign = vec[1].strip() if isinstance(vec[1], str) else None
    alt = _num(vec[7])
    if alt is None and len(vec) > 13:
        alt = _num(vec[13])
    return {
        "ts": ts,
        "icao24": icao24.lower(),
        "callsign": callsign or None,
        "country": vec[2] if isinstance(vec[2], str) else None,
        "lat": lat,
        "lon": lon,
        "alt_m": alt,
        "velocity": _num(vec[9]),
        "heading": _num(vec[10]),
    }


# --------------------------------------------------------------------------- fetch


def fetch(ctx: Ctx) -> Rows:
    payload = _states(ctx)
    epoch = _num(payload.get("time"))
    ts = datetime.fromtimestamp(epoch, tz=UTC) if epoch else ctx.now
    states = payload.get("states")
    if states is None:
        log.warning("opensky: no states in response")
        return [("aircraft_state", [])]
    if not isinstance(states, list):
        raise ValueError("opensky: states is not an array")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = 0
    for vec in states:
        row = _row(ts, vec)
        if row is None or row["icao24"] in seen:
            skipped += 1
            continue
        seen.add(row["icao24"])
        rows.append(row)
    if skipped:
        log.debug("opensky: %d vectors skipped (no position or malformed)", skipped)
    log.info("opensky: %d aircraft at %s", len(rows), ts.isoformat())
    return [("aircraft_state", rows)]


SOURCE = Source(
    name="opensky",
    interval=300,
    fetch=fetch,
    backfill=None,
    requires_env=["OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET"],
    tables=["aircraft_state"],
    description="OpenSky Network live aircraft states over Europe and the Middle East",
)

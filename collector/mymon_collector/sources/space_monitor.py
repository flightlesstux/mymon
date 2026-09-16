"""What's happening in near-Earth space and on Earth's surface right now — five keyless
public APIs, none Netherlands-specific:

- NASA EONET (``eonet.gsfc.nasa.gov``): open natural-hazard events (volcanoes, severe
  storms, sea/lake ice, floods, drought, landslides, temperature extremes, dust/haze).
  Wildfires are deliberately excluded — EONET carries thousands of small local fires
  (~7000 open at any time vs. ~70 for everything else combined), which would swamp the
  rest of this data on any shared map or table.
- The Space Devs' Launch Library 2 (``ll.thespacedevs.com``): upcoming and recently-flown
  orbital launches, worldwide.
- Open Notify (``api.open-notify.org``): the current crewed-spacecraft roster (ISS, and
  Tiangong when crewed).
- NOAA SWPC (``services.swpc.noaa.gov``): GOES primary satellite's 1-day X-ray flux
  (0.1-0.8nm / "long" channel), the standard input for solar flare classification
  (A/B/C/M/X, each a decade of flux in W/m^2). Only the single latest reading is kept —
  the upstream feed is 1-minute resolution, far finer than this source's poll interval.
- Celestrak (``celestrak.org``): count of actively tracked orbital objects. Celestrak
  caches each GROUP for 2 hours server-side and returns 403 (with a plain-text body, not
  an error the client can otherwise detect) if polled more often than that — this
  source's interval is set well above 2 hours specifically to stay clear of that, and a
  403 here is treated as a soft "nothing new this cycle", not a failure.

EONET/launches/astronauts land in their own tables (all live snapshots, not
backfillable — see retention.py); X-ray flux and satellite count are two more columns
on the existing space_weather table (see its ALTER TABLE comment in the schema).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

EONET_BASE = "https://eonet.gsfc.nasa.gov/api/v3/events"
LAUNCH_BASE = "https://ll.thespacedevs.com/2.3.0/launches"
ASTROS_URL = "http://api.open-notify.org/astros.json"
XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"

SOURCE_NAME = "space_monitor"

# EONET categories to keep — everything except wildfires (thousands of small local
# fires; see module docstring), manmade and waterColor (not natural hazards).
EONET_CATEGORIES = {
    "volcanoes", "severeStorms", "seaLakeIce", "floods", "drought", "landslides",
    "tempExtremes", "dustHaze",
}

# GOES long-channel (0.1-0.8nm) flux thresholds, W/m^2 -> flare class letter.
FLARE_THRESHOLDS = [(1e-4, "X"), (1e-5, "M"), (1e-6, "C"), (1e-7, "B")]


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _flare_class(flux: float) -> str | None:
    if flux <= 0:
        return None
    for threshold, letter in FLARE_THRESHOLDS:
        if flux >= threshold:
            return f"{letter}{flux / threshold:.1f}"
    return f"A{flux / 1e-8:.1f}"


# --------------------------------------------------------------------------- EONET


def _natural_event_rows(ctx: Ctx) -> list[dict[str, Any]]:
    resp = ctx.http.get(EONET_BASE, params={"status": "open", "limit": 2000})
    resp.raise_for_status()
    events = resp.json().get("events", [])
    rows: list[dict[str, Any]] = []
    for event in events:
        categories = event.get("categories") or []
        if not categories:
            continue
        category = categories[0]["id"]
        if category not in EONET_CATEGORIES:
            continue
        geometry = event.get("geometry") or []
        if not geometry:
            continue
        latest = geometry[-1]  # most recent known position/observation
        coords = latest.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        try:
            event_date = datetime.fromisoformat(latest["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            event_date = None
        rows.append({
            "id": event["id"],
            "title": event.get("title") or "",
            "category": category,
            "lat": lat,
            "lon": lon,
            "event_date": event_date,
            "magnitude_value": _num(latest.get("magnitudeValue")),
            "magnitude_unit": latest.get("magnitudeUnit"),
            "source": "eonet",
        })
    return rows


# --------------------------------------------------------------------------- launches


def _parse_launch(item: dict[str, Any]) -> dict[str, Any] | None:
    launch_id = item.get("id")
    if not launch_id:
        return None
    pad = item.get("pad") or {}
    location = pad.get("location") or {}
    status = item.get("status") or {}
    provider = item.get("launch_service_provider") or {}
    rocket = ((item.get("rocket") or {}).get("configuration") or {})
    mission = item.get("mission") or {}
    orbit = (mission.get("orbit") or {}) if mission else {}
    country = location.get("country") or {}
    try:
        net = datetime.fromisoformat((item.get("net") or "").replace("Z", "+00:00"))
    except ValueError:
        net = None
    return {
        "id": launch_id,
        "name": item.get("name") or "",
        "status": status.get("abbrev"),
        "provider": provider.get("name"),
        "rocket": rocket.get("full_name") or rocket.get("name"),
        "net": net,
        "pad_name": pad.get("name") or location.get("name"),
        "lat": _num(location.get("latitude")),
        "lon": _num(location.get("longitude")),
        "country": country.get("name") if isinstance(country, dict) else None,
        "orbit": orbit.get("name") if isinstance(orbit, dict) else None,
        "source": "thespacedevs",
    }


def _launch_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for endpoint in ("upcoming", "previous"):
        resp = ctx.http.get(f"{LAUNCH_BASE}/{endpoint}/", params={"limit": 20})
        resp.raise_for_status()
        for item in resp.json().get("results", []):
            row = _parse_launch(item)
            if row is not None:
                rows.append(row)
    return rows


# --------------------------------------------------------------------------- astronauts


def _astronaut_rows(ctx: Ctx) -> list[dict[str, Any]]:
    resp = ctx.http.get(ASTROS_URL)
    resp.raise_for_status()
    now = ctx.now.replace(tzinfo=UTC) if ctx.now.tzinfo is None else ctx.now
    rows: list[dict[str, Any]] = []
    for person in resp.json().get("people", []):
        name = person.get("name")
        if not name:
            continue
        rows.append({
            "name": name,
            "craft": person.get("craft"),
            "ts": now,
            "source": "open-notify",
        })
    return rows


# --------------------------------------------------------------------------- space weather


def _space_weather_rows(ctx: Ctx) -> list[dict[str, Any]]:
    # db.upsert() requires every row in a batch to share the same key set (it derives
    # the INSERT's column list from rows[0]), so both readings below always carry the
    # full {ts, xray_flux, xray_flare_class, satellites_active} shape even though they
    # come from different upstreams at different timestamps — unset metrics are None.
    rows: list[dict[str, Any]] = []

    resp = ctx.http.get(XRAY_URL)
    resp.raise_for_status()
    long_band = [r for r in resp.json() if r.get("energy") == "0.1-0.8nm" and _num(r.get("flux"))]
    if long_band:
        latest = long_band[-1]
        try:
            ts = datetime.fromisoformat(latest["time_tag"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            ts = None
        flux = _num(latest.get("flux"))
        if ts is not None and flux is not None:
            rows.append({"ts": ts, "xray_flux": flux, "xray_flare_class": _flare_class(flux),
                         "satellites_active": None})

    sat_resp = ctx.http.get(CELESTRAK_URL, params={"GROUP": "active", "FORMAT": "json"})
    if sat_resp.status_code == 403:
        log.info("space_monitor: celestrak 403 (2h cache not yet expired), skipping this cycle")
    else:
        sat_resp.raise_for_status()
        satellites = sat_resp.json()
        if isinstance(satellites, list) and satellites:
            now = ctx.now.replace(tzinfo=UTC) if ctx.now.tzinfo is None else ctx.now
            rows.append({"ts": now, "xray_flux": None, "xray_flare_class": None,
                         "satellites_active": len(satellites)})

    return rows


# --------------------------------------------------------------------------- source


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, str, Any], ...]
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    by_table: dict[str, list[dict[str, Any]]] = {}
    failures = 0
    for name, table, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("space_monitor: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.info("space_monitor: %s returned no rows", name)
            continue
        log.info("space_monitor: %s -> %d rows", name, len(part))
        by_table.setdefault(table, []).extend(part)
    return by_table, failures


def fetch(ctx: Ctx) -> Rows:
    by_table, failures = _run_upstreams(ctx, (
        ("natural_events", "natural_event", _natural_event_rows),
        ("launches", "space_launch", _launch_rows),
        ("astronauts", "astronaut", _astronaut_rows),
        ("space_weather", "space_weather", _space_weather_rows),
    ))
    if not by_table:
        raise RuntimeError("space_monitor: every upstream failed")
    log.info("space_monitor: %d tables populated (%d upstream failures)",
              len(by_table), failures)
    return list(by_table.items())


SOURCE = Source(
    name="space_monitor",
    interval=10800,  # 3h — comfortably above Celestrak's 2h server-side cache window
    fetch=fetch,
    backfill=None,
    tables=["natural_event", "space_launch", "astronaut", "space_weather"],
    description=(
        "Natural hazard events worldwide (NASA EONET, excl. wildfires), upcoming/"
        "recent orbital launches (Launch Library), who's currently in space (Open "
        "Notify), solar X-ray flux and flare class (NOAA SWPC), and the count of "
        "actively tracked orbital objects (Celestrak)."
    ),
)

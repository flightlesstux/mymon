"""Live bike-share station counts, worldwide — CityBikes (api.citybik.es), no key.

CityBikes lists 800+ networks but the list endpoint only carries metadata (no bike
counts) — getting live counts needs one request per network's detail endpoint. Polling
all 800+ every cycle is neither necessary nor polite, so this fetches a curated set of
~15 major-city networks, confirmed live against the actual network list (some guessed
IDs don't exist — e.g. there's no single "citibike-nyc", it's "citi-bike-nyc").

No historical endpoint upstream, so this is a live snapshot in ``bike_network`` with a
retention policy (see retention.py), same shape as aircraft_state/iss_position.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "bike_network"
BASE_URL = "https://api.citybik.es/v2/networks"

# network id -> display city (confirmed live against /v2/networks, 2026-09)
NETWORKS: dict[str, str] = {
    "velib": "Paris",
    "citi-bike-nyc": "New York",
    "santander-cycles": "London",
    "bicing": "Barcelona",
    "divvy": "Chicago",
    "capital-bikeshare": "Washington, DC",
    "callabike-berlin": "Berlin",
    "oslo-bysykkel": "Oslo",
    "ecobici-buenos-aires": "Buenos Aires",
    "bay-wheels": "San Francisco Bay Area",
    "bicimad": "Madrid",
    "bixi-toronto": "Toronto",
    "blue-bikes": "Boston",
    "velov": "Lyon",
    "stadtrad-hamburg-db": "Hamburg",
}


def fetch(ctx: Ctx) -> Rows:
    rows: list[dict[str, Any]] = []
    now = datetime.now(UTC).replace(tzinfo=None)
    for network_id, city in NETWORKS.items():
        resp = ctx.http.get(f"{BASE_URL}/{network_id}")
        if resp.status_code != 200:
            log.warning("bike_share: %s returned status %s", network_id, resp.status_code)
            continue
        network = resp.json().get("network")
        if not network:
            continue
        stations = network.get("stations", [])
        free_bikes = sum(s.get("free_bikes") or 0 for s in stations)
        empty_slots = sum(s.get("empty_slots") or 0 for s in stations)
        location = network.get("location", {})
        rows.append({
            "ts": now,
            "network_id": network_id,
            "city": city,
            "country": location.get("country"),
            "lat": location.get("latitude"),
            "lon": location.get("longitude"),
            "free_bikes": free_bikes,
            "empty_slots": empty_slots,
            "stations": len(stations),
            "source": "citybikes",
        })
    if not rows:
        raise RuntimeError("bike_share: every network failed")
    return [(TABLE, rows)]


SOURCE = Source(
    name="bike_share",
    interval=900,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Live bike-share station counts for 15 major cities worldwide (CityBikes): "
        "free bikes, empty docks, station counts."
    ),
)

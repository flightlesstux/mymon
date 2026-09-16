from datetime import datetime

import httpx
import respx

from mymon_collector.sources import bike_share as bs


def network_json(city, country, lat, lon, stations):
    return {"network": {
        "location": {"city": city, "country": country, "latitude": lat, "longitude": lon},
        "stations": stations,
    }}


@respx.mock
def test_fetch_aggregates_stations_per_network():
    for network_id, city in bs.NETWORKS.items():
        respx.get(f"{bs.BASE_URL}/{network_id}").mock(return_value=httpx.Response(
            200, json=network_json(city, "XX", 1.0, 2.0, [
                {"free_bikes": 5, "empty_slots": 3},
                {"free_bikes": 2, "empty_slots": 7},
            ])
        ))
    table, rows = bs.fetch(_ctx())[0]
    assert table == "bike_network"
    assert len(rows) == len(bs.NETWORKS)
    row = next(r for r in rows if r["network_id"] == "velib")
    assert row["free_bikes"] == 7
    assert row["empty_slots"] == 10
    assert row["stations"] == 2
    assert row["city"] == "Paris"
    assert row["source"] == "citybikes"


@respx.mock
def test_fetch_skips_failed_network_but_keeps_others():
    for network_id, city in bs.NETWORKS.items():
        if network_id == "velib":
            respx.get(f"{bs.BASE_URL}/{network_id}").mock(return_value=httpx.Response(500))
            continue
        respx.get(f"{bs.BASE_URL}/{network_id}").mock(return_value=httpx.Response(
            200, json=network_json(city, "XX", 1.0, 2.0, [{"free_bikes": 1, "empty_slots": 1}])
        ))
    table, rows = bs.fetch(_ctx())[0]
    assert len(rows) == len(bs.NETWORKS) - 1
    assert all(r["network_id"] != "velib" for r in rows)


def _ctx():
    return bs.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

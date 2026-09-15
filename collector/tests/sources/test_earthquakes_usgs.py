from datetime import UTC, datetime

import httpx
import respx

from mymon_collector.sources import earthquakes_usgs as mod
from tests.conftest import fixture_json

PK = {"id"}


@respx.mock
def test_fetch(ctx):
    respx.get(mod.FEED_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("earthquakes_usgs_all_day.json"))
    )
    out = mod.fetch(ctx)
    assert [t for t, _ in out] == ["earthquake"]
    rows = out[0][1]
    assert len(rows) == 4
    first = rows[0]
    assert first["id"] == "usgs:aka2026sibumr"
    assert first["ts"] == datetime(2026, 9, 15, 18, 4, 37, 731000, tzinfo=UTC)
    assert first["lat"] == 60.68
    assert first["lon"] == -150.202
    assert first["depth_km"] == 46
    assert first["mag"] == 1.7
    assert first["place"] == "29 km NW of Cooper Landing, Alaska"
    assert first["source"] == "usgs"
    assert all(PK <= r.keys() for r in rows)
    assert len({frozenset(r) for r in rows}) == 1


@respx.mock
def test_backfill(ctx):
    route = respx.get(url__regex=r"https://earthquake\.usgs\.gov/fdsnws/event/1/query\?.*").mock(
        return_value=httpx.Response(200, json=fixture_json("earthquakes_usgs_backfill.json"))
    )
    out = mod.backfill(ctx)
    assert [t for t, _ in out] == ["earthquake"]
    rows = out[0][1]
    assert len(rows) == 3
    assert rows[0]["id"] == "usgs:us7000thl5"
    assert rows[0]["mag"] == 4.7
    assert all(PK <= r.keys() for r in rows)
    params = route.calls.last.request.url.params
    assert params["starttime"] == "2025-09-15"
    assert params["minmagnitude"] == "4.5"
    assert params["limit"] == "20000"


@respx.mock
def test_skips_bad_feature(ctx):
    payload = fixture_json("earthquakes_usgs_all_day.json")
    payload["features"].append({"type": "Feature", "id": "bad", "properties": {}, "geometry": {}})
    payload["features"].append({"type": "Feature", "properties": {"time": 1}, "geometry": None})
    respx.get(mod.FEED_URL).mock(return_value=httpx.Response(200, json=payload))
    rows = mod.fetch(ctx)[0][1]
    assert len(rows) == 4

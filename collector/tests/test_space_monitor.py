from datetime import datetime

import httpx
import respx

from mymon_collector.sources import space_monitor as sm


def _ctx():
    return sm.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))


@respx.mock
def test_natural_event_rows_excludes_wildfires_and_uses_latest_geometry():
    respx.get(sm.EONET_BASE).mock(return_value=httpx.Response(200, json={"events": [
        {"id": "E1", "title": "Cyclone X", "categories": [{"id": "severeStorms"}],
         "geometry": [
             {"date": "2026-09-10T00:00:00Z", "coordinates": [1.0, 2.0],
              "magnitudeValue": 30, "magnitudeUnit": "kts"},
             {"date": "2026-09-11T00:00:00Z", "coordinates": [3.0, 4.0],
              "magnitudeValue": 50, "magnitudeUnit": "kts"},
         ]},
        {"id": "E2", "title": "Some Wildfire", "categories": [{"id": "wildfires"}],
         "geometry": [{"date": "2026-09-10T00:00:00Z", "coordinates": [5.0, 6.0]}]},
    ]}))
    rows = sm._natural_event_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["id"] == "E1"
    assert rows[0]["lat"] == 4.0  # from the later (last) geometry point
    assert rows[0]["lon"] == 3.0
    assert rows[0]["magnitude_value"] == 50


@respx.mock
def test_launch_rows_pulls_upcoming_and_previous():
    launch = {
        "id": "abc-123", "name": "Test Launch",
        "status": {"abbrev": "Go"},
        "launch_service_provider": {"name": "Test Provider"},
        "rocket": {"configuration": {"full_name": "Test Rocket"}},
        "net": "2026-09-16T13:33:53Z",
        "pad": {"name": "Pad 1", "location": {"name": "Test Site",
                 "latitude": 45.9, "longitude": 63.3, "country": {"name": "Kazakhstan"}}},
        "mission": {"orbit": {"name": "LEO"}},
    }
    respx.get(f"{sm.LAUNCH_BASE}/upcoming/").mock(
        return_value=httpx.Response(200, json={"results": [launch]}))
    respx.get(f"{sm.LAUNCH_BASE}/previous/").mock(
        return_value=httpx.Response(200, json={"results": [launch]}))
    rows = sm._launch_rows(_ctx())
    assert len(rows) == 2
    assert rows[0]["name"] == "Test Launch"
    assert rows[0]["lat"] == 45.9
    assert rows[0]["country"] == "Kazakhstan"
    assert rows[0]["orbit"] == "LEO"


@respx.mock
def test_astronaut_rows():
    respx.get(sm.ASTROS_URL).mock(return_value=httpx.Response(200, json={
        "people": [{"name": "Test Person", "craft": "ISS"}],
    }))
    rows = sm._astronaut_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["name"] == "Test Person"
    assert rows[0]["craft"] == "ISS"
    assert rows[0]["source"] == "open-notify"


@respx.mock
def test_space_weather_rows_shares_key_set_across_both_readings():
    respx.get(sm.XRAY_URL).mock(return_value=httpx.Response(200, json=[
        {"time_tag": "2026-09-16T08:30:00Z", "flux": 1.5e-6, "energy": "0.1-0.8nm"},
    ]))
    respx.get(sm.CELESTRAK_URL).mock(return_value=httpx.Response(200, json=[
        {"OBJECT_NAME": f"SAT-{i}"} for i in range(100)
    ]))
    rows = sm._space_weather_rows(_ctx())
    assert len(rows) == 2
    assert {frozenset(r.keys()) for r in rows} == {frozenset(rows[0].keys())}  # same shape
    xray_row = next(r for r in rows if r["xray_flux"] is not None)
    assert xray_row["xray_flare_class"] == "C1.5"
    sat_row = next(r for r in rows if r["satellites_active"] is not None)
    assert sat_row["satellites_active"] == 100


@respx.mock
def test_space_weather_rows_treats_celestrak_403_as_soft_skip():
    respx.get(sm.XRAY_URL).mock(return_value=httpx.Response(200, json=[]))
    respx.get(sm.CELESTRAK_URL).mock(
        return_value=httpx.Response(403, text="cache not expired"))
    rows = sm._space_weather_rows(_ctx())
    assert rows == []


def test_flare_class_thresholds():
    assert sm._flare_class(5e-5) == "M5.0"
    assert sm._flare_class(2e-4) == "X2.0"
    assert sm._flare_class(3e-7) == "B3.0"
    assert sm._flare_class(0) is None


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get(sm.EONET_BASE).mock(return_value=httpx.Response(200, json={"events": []}))
    respx.get(f"{sm.LAUNCH_BASE}/upcoming/").mock(return_value=httpx.Response(500))
    respx.get(f"{sm.LAUNCH_BASE}/previous/").mock(return_value=httpx.Response(500))
    respx.get(sm.ASTROS_URL).mock(return_value=httpx.Response(200, json={"people": [
        {"name": "Test Person", "craft": "ISS"},
    ]}))
    respx.get(sm.XRAY_URL).mock(return_value=httpx.Response(200, json=[]))
    respx.get(sm.CELESTRAK_URL).mock(return_value=httpx.Response(403))
    result = sm.fetch(_ctx())
    by_table = dict(result)
    assert "astronaut" in by_table
    assert "space_launch" not in by_table

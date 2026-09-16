from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_vehicles as ev
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_fleet_rows_for_fuel_covers_all_countries():
    data = jsonstat(
        ["geo", "time"], [2, 1], {"geo": ["DE", "TR"], "time": ["2023"]},
        {"0": 1200000, "1": 15000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/road_eqs_carpda").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ev._fleet_rows_for_fuel(_ctx(), "ELC", "electric")
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["DEU"] == 1200000
    assert by_country["TUR"] == 15000
    assert all(r["indicator"] == "vehicle_fleet_electric"
               and r["period_date"] == date(2023, 1, 1) for r in rows)


@respx.mock
def test_fetch_covers_all_five_fuel_types():
    data = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2023"]}, {"0": 100})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/road_eqs_carpda").mock(
        return_value=httpx.Response(200, json=data)
    )
    table, rows = ev.fetch(_ctx())[0]
    indicators = {r["indicator"] for r in rows}
    for slug in ev.FUEL_CODES.values():
        assert f"vehicle_fleet_{slug}" in indicators


@respx.mock
def test_fetch_survives_one_fuel_type_failing():
    ok = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2023"]}, {"0": 100})

    def responder(request):
        if "PET" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, json=ok)

    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/road_eqs_carpda").mock(
        side_effect=responder
    )
    table, rows = ev.fetch(_ctx())[0]
    assert not any(r["indicator"] == "vehicle_fleet_petrol" for r in rows)
    assert any(r["indicator"] == "vehicle_fleet_diesel" for r in rows)


def _ctx():
    return ev.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

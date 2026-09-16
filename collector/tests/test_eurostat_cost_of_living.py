from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_cost_of_living as ecl
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_category_rows_maps_geo_to_iso3():
    data = jsonstat(
        ["geo", "time"], [2, 1], {"geo": ["DE", "TR"], "time": ["2026-01"]},
        {"0": 120.0, "1": 210.0},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ecl._category_rows(_ctx(), "CP04", "housing_water_energy")
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["DEU"] == 120.0
    assert by_country["TUR"] == 210.0
    assert all(r["indicator"] == "cpi_cat_housing_water_energy"
               and r["period_date"] == date(2026, 1, 1) for r in rows)


def test_categories_covers_all_12():
    assert len(ecl.CATEGORIES) == 12
    assert ecl.CATEGORIES["CP04"] == "housing_water_energy"
    assert ecl.CATEGORIES["CP11"] == "restaurants_and_hotels"


@respx.mock
def test_fetch_survives_one_category_failing():
    ok = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2026-01"]}, {"0": 100.0})

    def responder(request):
        if "CP01" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, json=ok)

    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        side_effect=responder
    )
    table, rows = ecl.fetch(_ctx())[0]
    assert table == "price_index"
    assert not any(r["indicator"] == "cpi_cat_food_and_drink" for r in rows)
    assert any(r["indicator"] == "cpi_cat_health" for r in rows)


def _ctx():
    return ecl.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

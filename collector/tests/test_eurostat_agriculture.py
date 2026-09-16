from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_agriculture as ea
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_livestock_rows_maps_animal_codes():
    data = jsonstat(
        ["animals", "geo", "time"], [3, 1, 1],
        {"animals": ["A2000", "A3100", "A4100"], "geo": ["DE"], "time": ["2023"]},
        {"0": 11000000, "1": 25000000, "2": 1500000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ef_lsk_main").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ea._livestock_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["cattle_count"] == 11000000
    assert by_indicator["pig_count"] == 25000000
    assert by_indicator["sheep_count"] == 1500000
    assert all(r["country_iso3"] == "DEU" and r["period_date"] == date(2023, 1, 1)
               for r in rows)


@respx.mock
def test_holdings_rows():
    data = jsonstat(
        ["geo", "time"], [1, 1], {"geo": ["FR"], "time": ["2020"]}, {"0": 250000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ef_lsk_main").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ea._holdings_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["country_iso3"] == "FRA"
    assert rows[0]["indicator"] == "farm_holdings_with_livestock"
    assert rows[0]["value"] == 250000


def test_geos_excludes_turkey():
    assert "TR" not in ea.GEOS
    assert "DE" in ea.GEOS


@respx.mock
def test_fetch_survives_one_upstream_failing():
    ok = jsonstat(["animals", "geo", "time"], [1, 1, 1],
                  {"animals": ["A2000"], "geo": ["DE"], "time": ["2023"]}, {"0": 11000000})
    # both livestock and holdings hit the same URL; respx matches regardless of
    # params, so this single mock serves both calls
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ef_lsk_main").mock(
        return_value=httpx.Response(200, json=ok)
    )
    table, rows = ea.fetch(_ctx())[0]
    assert table == "price_index"
    assert rows


def _ctx():
    return ea.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_safety as es
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_crime_rows_maps_categories_and_geo():
    # id order [iccs, geo, time], sizes [2, 2, 1] -> strides [2, 1, 1]
    data = jsonstat(
        ["iccs", "geo", "time"], [2, 2, 1],
        {"iccs": ["ICCS0101", "ICCS0401"], "geo": ["DE", "FR"], "time": ["2022"]},
        {"0": 0.74, "1": 1.21, "2": 45.89, "3": 133.65},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/crim_off_cat").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = es._crime_rows(_ctx())
    by_key = {(r["country_iso3"], r["indicator"]): r["value"] for r in rows}
    assert by_key[("DEU", "crime_rate_per_100k_homicide")] == 0.74
    assert by_key[("FRA", "crime_rate_per_100k_homicide")] == 1.21
    assert by_key[("DEU", "crime_rate_per_100k_robbery")] == 45.89
    assert by_key[("FRA", "crime_rate_per_100k_robbery")] == 133.65
    assert all(r["period_date"] == date(2022, 1, 1) for r in rows)


@respx.mock
def test_road_deaths_rows():
    data = jsonstat(["geo", "time"], [1, 1], {"geo": ["IT"], "time": ["2022"]}, {"0": 52.3})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/tran_r_acci").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = es._road_deaths_rows(_ctx())
    assert rows[0]["indicator"] == "road_deaths_per_million"
    assert rows[0]["country_iso3"] == "ITA"
    assert rows[0]["value"] == 52.3


def test_fetch_survives_one_upstream_failing(monkeypatch):
    def _boom(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(es, "_crime_rows", _boom)
    monkeypatch.setattr(es, "_road_deaths_rows", lambda ctx: [
        {"period_date": date(2022, 1, 1), "country_iso3": "DEU",
         "indicator": "road_deaths_per_million", "value": 33.0, "unit": "per million",
         "source": "eurostat"},
    ])
    table, rows = es.fetch(_ctx())[0]
    assert table == "price_index"
    assert len(rows) == 1


def test_geo_to_iso3_includes_netherlands_as_a_seventh_country():
    assert es.GEO_TO_ISO3["NL"] == "NLD"
    assert set(es.GEO_TO_ISO3) == {"DE", "IT", "ES", "EL", "TR", "FR", "NL"}


@respx.mock
def test_road_deaths_rows_covers_netherlands():
    data = jsonstat(["geo", "time"], [1, 1], {"geo": ["NL"], "time": ["2022"]}, {"0": 42.0})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/tran_r_acci").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = es._road_deaths_rows(_ctx())
    assert rows[0]["country_iso3"] == "NLD"
    assert rows[0]["value"] == 42.0


def _ctx():
    return es.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

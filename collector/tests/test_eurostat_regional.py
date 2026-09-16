from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_regional as er
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_unemployment_rows_filters_to_nuts2_codes_of_our_six_countries():
    # DE21 is a real NUTS2 code (kept); DE111 is NUTS3-length (dropped); XX99 has no
    # matching country prefix (dropped); TR10 is a real NUTS2 code (kept).
    data = jsonstat(
        ["geo", "time"], [4, 1],
        {"geo": ["DE21", "DE111", "TR10", "XX99"], "time": ["2023"]},
        {"0": 10.5, "1": 99.9, "2": 11.1, "3": 50.0},
    )
    respx.get(
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfst_r_lfu3rt"
    ).mock(return_value=httpx.Response(200, json=data))
    rows = er._unemployment_rows(_ctx())
    by_indicator = {r["indicator"]: r for r in rows}
    assert set(by_indicator) == {"regional_unemployment_pct_DE21", "regional_unemployment_pct_TR10"}
    assert by_indicator["regional_unemployment_pct_DE21"]["value"] == 10.5
    assert by_indicator["regional_unemployment_pct_DE21"]["country_iso3"] == "DEU"
    assert by_indicator["regional_unemployment_pct_TR10"]["value"] == 11.1
    assert by_indicator["regional_unemployment_pct_TR10"]["country_iso3"] == "TUR"
    assert all(r["period_date"] == date(2023, 1, 1) for r in rows)


def test_region_iso3_matches_only_four_char_nuts2_codes():
    assert er._region_iso3("DE21") == "DEU"
    assert er._region_iso3("ITC1") == "ITA"
    assert er._region_iso3("DE111") is None  # NUTS3, not NUTS2
    assert er._region_iso3("DE1") is None  # NUTS1
    assert er._region_iso3("US01") is None  # not one of our six countries


def test_fetch_survives_one_indicator_failing(monkeypatch):
    def _boom(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(er, "_unemployment_rows", _boom)
    monkeypatch.setattr(er, "_gdp_per_capita_rows", lambda ctx: [
        {"period_date": date(2023, 1, 1), "country_iso3": "DEU",
         "indicator": "regional_gdp_per_capita_eur_DE21", "value": 50000.0, "unit": "EUR",
         "source": "eurostat"},
    ])
    monkeypatch.setattr(er, "_population_rows", lambda ctx: [])
    table, rows = er.fetch(_ctx())[0]
    assert table == "price_index"
    assert len(rows) == 1
    assert rows[0]["indicator"] == "regional_gdp_per_capita_eur_DE21"


def _ctx():
    return er.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

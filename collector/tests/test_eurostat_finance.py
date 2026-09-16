from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_finance as ef
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_govt_debt_and_deficit_rows():
    data = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2023"]}, {"0": 62.3})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ef._govt_debt_rows(_ctx())
    assert rows[0]["indicator"] == "govt_debt_pct_gdp"
    assert rows[0]["value"] == 62.3
    assert rows[0]["period_date"] == date(2023, 1, 1)


@respx.mock
def test_minimum_wage_rows_maps_half_year_codes():
    data = jsonstat(
        ["geo", "time"], [1, 2], {"geo": ["FR"], "time": ["2024-S1", "2024-S2"]},
        {"0": 1766.9, "1": 1801.8},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/earn_mw_cur").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ef._minimum_wage_rows(_ctx())
    by_period = {r["period_date"]: r["value"] for r in rows}
    assert by_period[date(2024, 1, 1)] == 1766.9
    assert by_period[date(2024, 7, 1)] == 1801.8
    assert all(r["indicator"] == "minimum_wage_eur_month" for r in rows)


@respx.mock
def test_exports_and_imports_rows():
    data = jsonstat(["geo", "time"], [1, 1], {"geo": ["ES"], "time": ["2023"]}, {"0": 566403.0})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ef._exports_rows(_ctx())
    assert rows[0]["indicator"] == "exports_goods_services_meur"
    assert rows[0]["country_iso3"] == "ESP"


def test_fetch_survives_one_upstream_failing(monkeypatch):
    def _boom(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(ef, "_govt_debt_rows", _boom)
    monkeypatch.setattr(ef, "_govt_deficit_rows", lambda ctx: [])
    monkeypatch.setattr(ef, "_minimum_wage_rows", lambda ctx: [
        {"period_date": date(2024, 1, 1), "country_iso3": "DEU",
         "indicator": "minimum_wage_eur_month", "value": 2054.0, "unit": "EUR",
         "source": "eurostat"},
    ])
    monkeypatch.setattr(ef, "_exports_rows", lambda ctx: [])
    monkeypatch.setattr(ef, "_imports_rows", lambda ctx: [])
    table, rows = ef.fetch(_ctx())[0]
    assert table == "price_index"
    assert len(rows) == 1


def test_geo_to_iso3_includes_netherlands_as_a_seventh_country():
    assert ef.GEO_TO_ISO3["NL"] == "NLD"
    assert set(ef.GEO_TO_ISO3) == {"DE", "IT", "ES", "EL", "TR", "FR", "NL"}


@respx.mock
def test_govt_debt_rows_covers_netherlands():
    data = jsonstat(["geo", "time"], [1, 1], {"geo": ["NL"], "time": ["2023"]}, {"0": 45.8})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ef._govt_debt_rows(_ctx())
    assert rows[0]["country_iso3"] == "NLD"
    assert rows[0]["value"] == 45.8


def _ctx():
    return ef.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_energy as ee
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_gas_price_rows_maps_half_year_to_month():
    data = jsonstat(
        ["geo", "time"], [1, 2], {"geo": ["DE"], "time": ["2024-S1", "2024-S2"]},
        {"0": 0.0613, "1": 0.0700},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_202").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ee._gas_price_rows(_ctx())
    by_date = {r["period_date"]: r["value"] for r in rows}
    assert by_date[date(2024, 1, 1)] == 0.0613
    assert by_date[date(2024, 7, 1)] == 0.0700
    assert all(r["indicator"] == "gas_price_eur_per_kwh" and r["country_iso3"] == "DEU"
               for r in rows)


@respx.mock
def test_production_mix_rows_maps_siec_codes():
    data = jsonstat(
        ["siec", "geo", "time"], [3, 1, 1],
        {"siec": ["TOTAL", "RA300", "N9000"], "geo": ["FR"], "time": ["2023"]},
        {"0": 500000, "1": 40000, "2": 300000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_ind_peh").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ee._production_mix_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["electricity_production_gwh_total"] == 500000
    assert by_indicator["electricity_production_gwh_wind"] == 40000
    assert by_indicator["electricity_production_gwh_nuclear"] == 300000
    assert all(r["country_iso3"] == "FRA" for r in rows)


@respx.mock
def test_fetch_survives_one_upstream_failing():
    ok = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2024-S1"]}, {"0": 0.06})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_202").mock(
        return_value=httpx.Response(200, json=ok)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_pc_204").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nrg_ind_peh").mock(
        return_value=httpx.Response(500)
    )
    table, rows = ee.fetch(_ctx())[0]
    assert table == "price_index"
    assert any(r["indicator"] == "gas_price_eur_per_kwh" for r in rows)


def _ctx():
    return ee.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

from datetime import datetime

import httpx
import respx

from mymon_collector.sources import energy_grid as eg


@respx.mock
def test_dk_rows_parses_mix_and_consumption():
    respx.get(eg.ENERGI_BASE).mock(return_value=httpx.Response(200, json={"records": [
        {"HourUTC": "2026-09-07T06:00:00", "PriceArea": "DK1",
         "OffshoreWindLt100MW_MWh": 10, "OffshoreWindGe100MW_MWh": 20,
         "OnshoreWindLt50kW_MWh": 1, "OnshoreWindGe50kW_MWh": 2,
         "SolarPowerLt10kW_MWh": 3, "SolarPowerGe10Lt40kW_MWh": 1,
         "SolarPowerGe40kW_MWh": 5, "SolarPowerSelfConMWh": 1,
         "CentralPowerMWh": 100, "GrossConsumptionMWh": 500},
    ]}))
    rows = eg._dk_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["wind_generation_mwh"] == 33
    assert by_indicator["solar_generation_mwh"] == 10
    assert by_indicator["central_power_mwh"] == 100
    assert by_indicator["gross_consumption_mwh"] == 500
    assert all(r["region"] == "DK1" and r["source"] == "energidataservice" for r in rows)


@respx.mock
def test_uk_rows_parses_actual_and_forecast():
    respx.get(eg.CARBON_BASE).mock(return_value=httpx.Response(200, json={"data": [
        {"from": "2026-09-16T08:00Z", "to": "2026-09-16T08:30Z",
         "intensity": {"forecast": 132, "actual": 129, "index": "moderate"}},
    ]}))
    rows = eg._uk_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["carbon_intensity_gco2_kwh"] == 129
    assert by_indicator["carbon_intensity_forecast_gco2_kwh"] == 132
    assert all(r["region"] == "GB" for r in rows)


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get(eg.ENERGI_BASE).mock(return_value=httpx.Response(500))
    respx.get(eg.CARBON_BASE).mock(return_value=httpx.Response(200, json={"data": [
        {"from": "2026-09-16T08:00Z", "intensity": {"forecast": 132, "actual": 129}},
    ]}))
    table, rows = eg.fetch(_ctx())[0]
    assert table == "energy_grid"
    assert all(r["region"] == "GB" for r in rows)


def _ctx():
    return eg.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

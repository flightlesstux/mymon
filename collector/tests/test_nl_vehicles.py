from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import nl_vehicles as nv


def cbs_json(records):
    return {"value": records}


SAMPLE_FLEET_ROW = {
    "Perioden": "2022JJ00", "TotaalNederland_1": 8941456,
    "Benzine_15": 7108139, "Diesel_16": 989894, "LPG_17": 105138,
    "Elektriciteit_18": 725610, "CNG_19": 8961,
}


@respx.mock
def test_fleet_rows_merges_both_tables_and_dedupes_overlap():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/71405ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([SAMPLE_FLEET_ROW]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85237NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {**SAMPLE_FLEET_ROW, "Elektriciteit_18": 999999},  # newer table wins on overlap
        ]))
    )
    table, rows = nv.fetch(_ctx())[0]
    ev_rows = [r for r in rows if r["indicator"] == "vehicle_fleet_electric"
               and r["period_date"] == date(2022, 1, 1)]
    assert len(ev_rows) == 1
    assert ev_rows[0]["value"] == 999999  # 85237NED's row, fetched after 71405ned's


@respx.mock
def test_fleet_rows_covers_all_fuel_types():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/71405ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([SAMPLE_FLEET_ROW]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85237NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    table, rows = nv.fetch(_ctx())[0]
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["vehicle_fleet_total"] == 8941456
    assert by_indicator["vehicle_fleet_petrol"] == 7108139
    assert by_indicator["vehicle_fleet_diesel"] == 989894
    assert by_indicator["vehicle_fleet_lpg"] == 105138
    assert by_indicator["vehicle_fleet_electric"] == 725610
    assert by_indicator["vehicle_fleet_cng"] == 8961


@respx.mock
def test_marina_capacity_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/84133NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2021JJ00", "TotaalJachthavens_1": 400,
             "TotaalZomerligplaatsen_2": 68100, "TotaalPassantenovernachtingen_6": 450000},
        ]))
    )
    rows = nv._marina_capacity_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["marina_count"] == 400
    assert by_indicator["marina_berths"] == 68100
    assert by_indicator["marina_visitor_overnight_stays"] == 450000


@respx.mock
def test_marina_finance_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/84132NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2021JJ00", "TotaalWerkzamePersonen_5": 1052, "TotaalBaten_11": 130},
        ]))
    )
    rows = nv._marina_finance_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["marina_employees"] == 1052
    assert by_indicator["marina_revenue_mln_eur"] == 130


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/71405ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([SAMPLE_FLEET_ROW]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85237NED/TypedDataSet").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/84133NED/TypedDataSet").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/84132NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    table, rows = nv.fetch(_ctx())[0]
    assert table == "price_index"
    assert any(r["indicator"] == "vehicle_fleet_total" for r in rows)


def _ctx():
    return nv.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

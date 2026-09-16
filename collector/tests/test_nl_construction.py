from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import nl_construction as nc


def cbs_json(records):
    return {"value": records}


@respx.mock
def test_turnover_rows_skips_quarterly_rollups():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85809NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026KW03", "IndexcijfersOmzet_1": 999.0,
             "OmzetontwikkelingTOVEenJaarEerder_2": 999.0},
            {"Perioden": "2026MM07", "IndexcijfersOmzet_1": 143.5,
             "OmzetontwikkelingTOVEenJaarEerder_2": 3.6},
        ]))
    )
    rows = nc._turnover_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["construction_turnover_index"] == 143.5
    assert by_indicator["construction_turnover_yoy_pct"] == 3.6
    assert all(r["period_date"] == date(2026, 7, 1) for r in rows)


@respx.mock
def test_building_cost_input_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80444ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026MM07", "Prijsindex_1": 150.0, "Prijsindex_3": 160.0,
             "Prijsindex_5": 140.0},
        ]))
    )
    rows = nc._building_cost_input_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["building_cost_input_index"] == 150.0
    assert by_indicator["building_cost_input_wage_index"] == 160.0
    assert by_indicator["building_cost_input_material_index"] == 140.0


@respx.mock
def test_building_cost_output_rows_keeps_only_annual():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80334ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "1914JJ00", "Index_1": 1.8, "Index_3": 1.7},
            {"Perioden": "2025KW04", "Index_1": 999.0, "Index_3": 999.0},
            {"Perioden": "2025JJ00", "Index_1": 197.4, "Index_3": 190.0},
        ]))
    )
    rows = nc._building_cost_output_rows(_ctx())
    dates = {r["period_date"] for r in rows}
    assert dates == {date(1914, 1, 1), date(2025, 1, 1)}
    by_year = {(r["period_date"], r["indicator"]): r["value"] for r in rows}
    assert by_year[(date(2025, 1, 1), "building_cost_output_index_incl_vat")] == 197.4


@respx.mock
def test_building_permits_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83667NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026MM06", "Bouwkosten_1": 4611, "Bouwvergunningen_2": 2521},
        ]))
    )
    rows = nc._building_permits_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["building_permits_cost_mln_eur"] == 4611
    assert by_indicator["building_permits_count"] == 2521


@respx.mock
def test_bankruptcy_total_rows_skips_quarterly_rollups():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82242NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "1981KW01", "UitgesprokenFaillissementen_1": 3201.0},
            {"Perioden": "1981MM01", "UitgesprokenFaillissementen_1": 213.0},
        ]))
    )
    rows = nc._bankruptcy_total_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["value"] == 213.0
    assert rows[0]["period_date"] == date(1981, 1, 1)


@respx.mock
def test_bankruptcy_sector_rows_covers_all_thirteen_sectors():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82244NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026MM08", "UitgesprokenFaillissementen_1": 50.0},
        ]))
    )
    rows = nc._bankruptcy_sector_rows(_ctx())
    indicators = {r["indicator"] for r in rows}
    for slug in nc.BANKRUPTCY_SECTORS.values():
        assert f"bankruptcies_sector_{slug}" in indicators
    assert len(rows) == len(nc.BANKRUPTCY_SECTORS)


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85809NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026MM07", "IndexcijfersOmzet_1": 143.5,
             "OmzetontwikkelingTOVEenJaarEerder_2": 3.6},
        ]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80444ned/TypedDataSet").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80334ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83667NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82242NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82244NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    table, rows = nc.fetch(_ctx())[0]
    assert table == "price_index"
    assert any(r["indicator"] == "construction_turnover_index" for r in rows)


def _ctx():
    return nc.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

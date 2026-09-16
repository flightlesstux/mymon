from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import nl_ports as np


def cbs_json(records):
    return {"value": records}


@respx.mock
def test_port_cargo_rows_covers_all_four_ports():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85598NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025KW04", "BrutoplusgewichtOvergeslagenGoederen_1": 111305},
        ]))
    )
    rows = np._port_cargo_rows(_ctx())
    assert {r["port_code"] for r in rows} == set(np.PORTS)
    assert all(r["indicator"] == "cargo_1000t" and r["value"] == 111305 for r in rows)
    assert all(r["period_date"] == date(2025, 10, 1) for r in rows)


@respx.mock
def test_port_ship_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85602NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2024JJ00", "Zeeschepen_1": 25600},
        ]))
    )
    rows = np._port_ship_rows(_ctx())
    assert all(r["indicator"] == "ship_calls" and r["value"] == 25600 for r in rows)
    assert len(rows) == len(np.PORTS)


@respx.mock
def test_container_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85601NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026KW01", "OvergeslagenContainers_1": 3601,
             "BrutoplusgewichtOvergeslagenContainers_2": 33049},
        ]))
    )
    rows = np._container_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["containers_1000teu"] == 3601
    assert by_indicator["container_cargo_1000t"] == 33049


@respx.mock
def test_freight_mode_rows_covers_all_six_modes():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83101NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2024JJ00", "Vervoerwijzen": code, "TotaalGoederenvervoer_1": 100,
             "AanvoerNaarNederland_4": 40, "AfvoerNaarBuitenland_5": 60}
            for code in np.FREIGHT_MODES
        ]))
    )
    rows = np._freight_mode_rows(_ctx())
    indicators = {r["indicator"] for r in rows}
    for name in np.FREIGHT_MODES.values():
        assert f"freight_total_mt_{name}" in indicators
        assert f"freight_import_mt_{name}" in indicators
        assert f"freight_export_mt_{name}" in indicators
    assert len(rows) == len(np.FREIGHT_MODES) * 3


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85601NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025KW01", "OvergeslagenContainers_1": 3000,
             "BrutoplusgewichtOvergeslagenContainers_2": 30000},
        ]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83101NED/TypedDataSet").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85598NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025KW01", "BrutoplusgewichtOvergeslagenGoederen_1": 100000},
        ]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85602NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    result = np.fetch(_ctx())
    by_table = dict(result)
    assert any(r["indicator"] == "containers_1000teu" for r in by_table["price_index"])
    assert any(r["indicator"] == "cargo_1000t" for r in by_table["port_metric"])


def _ctx():
    return np.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

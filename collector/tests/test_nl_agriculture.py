from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import nl_agriculture as ag


def cbs_json(records):
    return {"value": records}


SAMPLE_ROW = {
    "Perioden": "2025JJ00",
    "AantalLandbouwbedrijvenTotaal_1": 49080,
    "CultuurgrondTotaal_3": 1800000,
    "Akkerbouw_4": 600000,
    "TuinbouwOpenGrond_5": 90000,
    "TuinbouwOnderGlas_6": 10000,
    "GraslandEnGroenvoedergewassen_7": 1100000,
    "RundveeTotaal_466": 3643800,
    "VarkensTotaal_573": 9765590,
    "KippenTotaal_591": 87721700,
}


@respx.mock
def test_national_rows_covers_all_columns():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/81302ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([SAMPLE_ROW]))
    )
    rows = ag._national_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["farm_count"] == 49080
    assert by_indicator["cattle_count"] == 3643800
    assert by_indicator["pig_count"] == 9765590
    assert by_indicator["chicken_count"] == 87721700
    assert all(r["unit"] in ("count", "ha") for r in rows)
    assert all(r["period_date"] == date(2025, 1, 1) for r in rows)


@respx.mock
def test_regional_rows_keeps_only_provinces_and_uses_are_unit():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80780ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {**SAMPLE_ROW, "RegioS": "PV20  "},
            {**SAMPLE_ROW, "RegioS": "NL01  "},
            {**SAMPLE_ROW, "RegioS": "GM0363"},
        ]))
    )
    rows = ag._regional_rows(_ctx())
    assert {r["region_code"] for r in rows} == {"PV20"}
    by_indicator = {r["indicator"]: r for r in rows}
    assert by_indicator["farm_count"]["unit"] == "count"
    assert by_indicator["agricultural_land"]["unit"] == "are"  # not "ha", per source unit


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/81302ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([SAMPLE_ROW]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80780ned/TypedDataSet").mock(
        return_value=httpx.Response(500)
    )
    result = ag.fetch(_ctx())
    by_table = dict(result)
    assert by_table["price_index"]
    assert by_table["region_metric"] == []


def _ctx():
    return ag.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

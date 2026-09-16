from datetime import date, datetime
from pathlib import Path

import httpx
import respx

from mymon_collector.sources import nl_metrics as nl

FIXTURES = Path(__file__).parent / "fixtures"


def cbs_json(records):
    return {"value": records}


@respx.mock
def test_cpi_rows_headline_food_and_all_categories():
    # One generic response regardless of which category's filter is requested — the
    # value itself doesn't matter here, only that every category's request is parsed and
    # lands under the right indicator name.
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83131NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025MM01", "CPI_1": 131.35, "JaarmutatieCPI_5": 3.3},
        ]))
    )
    rows = nl._cpi_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["cpi_index"] == 131.35
    assert by_indicator["cpi_inflation_pct"] == 3.3
    assert by_indicator["food_cpi_index"] == 131.35
    assert by_indicator["food_cpi_inflation_pct"] == 3.3
    # every one of the 12 COICOP categories produced an index-only row, no YoY
    for slug in nl.CPI_CATEGORIES.values():
        assert by_indicator[f"cpi_cat_{slug}"] == 131.35
        assert f"cpi_cat_{slug}_yoy" not in by_indicator
    assert len(nl.CPI_CATEGORIES) == 12
    assert all(r["country_iso3"] == "NLD" and r["period_date"] == date(2025, 1, 1) for r in rows)


@respx.mock
def test_rent_rows_parses_annual_period():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/70675ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025JJ00", "Huurverhoging_1": 5.3},
        ]))
    )
    rows = nl._rent_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["indicator"] == "rent_increase_pct"
    assert rows[0]["value"] == 5.3
    assert rows[0]["period_date"] == date(2025, 1, 1)


@respx.mock
def test_house_price_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85773NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025MM01", "PrijsindexVerkoopprijzen_1": 145.5,
             "GemiddeldeVerkoopprijs_7": 474534, "VerkochteWoningen_4": 17907},
        ]))
    )
    rows = nl._house_price_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["house_price_index"] == 145.5
    assert by_indicator["house_price_avg_eur"] == 474534
    assert by_indicator["house_sales_count"] == 17907


@respx.mock
def test_energy_rows_filters_incl_vat_only():
    respx.get(
        "https://opendata.cbs.nl/ODataApi/odata/85592NED/TypedDataSet",
        params={"$filter": "Btw eq 'A048944'"},
    ).mock(return_value=httpx.Response(200, json=cbs_json([
        {"Perioden": "2025MM01", "VariabelLeveringstariefContractprijs_3": 0.6332,
         "VariabelLeveringstariefContractprijs_9": 0.1589},
    ])))
    rows = nl._energy_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["gas_variable_price_eur_m3"] == 0.6332
    assert by_indicator["electricity_variable_price_eur_kwh"] == 0.1589


@respx.mock
def test_unemployment_rows_uses_seasonally_adjusted():
    respx.get(
        "https://opendata.cbs.nl/ODataApi/odata/80590ned/TypedDataSet",
        params={"$filter": "Geslacht eq 'T001038' and Leeftijd eq '52052   '"},
    ).mock(return_value=httpx.Response(200, json=cbs_json([
        {"Perioden": "2025MM01", "NietSeizoengecorrigeerd_7": 4.0, "Seizoengecorrigeerd_8": 3.8},
    ])))
    rows = nl._unemployment_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["indicator"] == "unemployment_rate_pct"
    assert rows[0]["value"] == 3.8


@respx.mock
def test_tourism_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82058NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025MM01", "Totaal_1": 2888, "Totaal_4": 6878, "Bezettingsgraad_7": 23.4},
        ]))
    )
    rows = nl._tourism_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["tourism_guests_thousands"] == 2888
    assert by_indicator["tourism_overnight_stays_thousands"] == 6878
    assert by_indicator["tourism_occupancy_pct"] == 23.4


@respx.mock
def test_bond_yield_rows_parses_ecb_csv():
    respx.get("https://data-api.ecb.europa.eu/service/data/IRS/M.NL.L.L40.CI.0000.EUR.N.Z").mock(
        return_value=httpx.Response(200, text=(FIXTURES / "nl_metrics_ecb_irs.csv").read_text())
    )
    rows = nl._bond_yield_rows(_ctx())
    assert len(rows) == 3
    aug = next(r for r in rows if r["period_date"] == date(2026, 8, 1))
    assert aug["indicator"] == "gov_bond_10y_pct"
    assert aug["value"] == 3.285
    assert aug["source"] == "ecb"


@respx.mock
def test_fetch_survives_one_upstream_failing():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83131NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025MM01", "CPI_1": 131.35, "JaarmutatieCPI_5": 3.3},
        ]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/70675ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85773NED/TypedDataSet").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85592NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80590ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82058NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://data-api.ecb.europa.eu/service/data/IRS/M.NL.L.L40.CI.0000.EUR.N.Z").mock(
        return_value=httpx.Response(200, text=(FIXTURES / "nl_metrics_ecb_irs.csv").read_text())
    )
    result = nl.fetch(_ctx())
    table, rows = result[0]
    assert table == "price_index"
    indicators = {r["indicator"] for r in rows}
    assert "cpi_index" in indicators
    assert "gov_bond_10y_pct" in indicators


def _ctx():
    return nl.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

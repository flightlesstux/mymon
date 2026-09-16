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
def test_house_price_regional_rows_keeps_only_provinces():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85792NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"RegioS": "PV27  ", "Perioden": "2025KW02", "PrijsindexVerkoopprijzen_1": 140.4,
             "GemiddeldeVerkoopprijs_7": 557670, "VerkochteWoningen_4": 1234},
            {"RegioS": "NL01  ", "Perioden": "2025KW02", "PrijsindexVerkoopprijzen_1": 148.7,
             "GemiddeldeVerkoopprijs_7": 472710, "VerkochteWoningen_4": 9999},
            {"RegioS": "GM0363", "Perioden": "2025KW02", "PrijsindexVerkoopprijzen_1": 132.4,
             "GemiddeldeVerkoopprijs_7": 612399, "VerkochteWoningen_4": 555},
        ]))
    )
    rows = nl._house_price_regional_rows(_ctx())
    assert {r["region_code"] for r in rows} == {"PV27"}  # NL01 and GM0363 dropped
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["house_price_index"] == 140.4
    assert by_indicator["house_price_avg_eur"] == 557670
    assert by_indicator["house_sales_count"] == 1234
    assert all(r["period_date"] == date(2025, 4, 1) for r in rows)  # 2025KW02 -> April 1


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
def test_unemployment_rows_also_emits_participation_rate():
    respx.get(
        "https://opendata.cbs.nl/ODataApi/odata/80590ned/TypedDataSet",
        params={"$filter": "Geslacht eq 'T001038' and Leeftijd eq '52052   '"},
    ).mock(return_value=httpx.Response(200, json=cbs_json([
        {"Perioden": "2025MM01", "Seizoengecorrigeerd_8": 3.8, "Seizoengecorrigeerd_14": 72.1},
    ])))
    rows = nl._unemployment_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["unemployment_rate_pct"] == 3.8
    assert by_indicator["labour_participation_pct"] == 72.1


@respx.mock
def test_labour_breakdown_rows_covers_age_and_gender():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80590ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025MM01", "Seizoengecorrigeerd_8": 5.5},
        ]))
    )
    rows = nl._labour_breakdown_rows(_ctx())
    indicators = {r["indicator"] for r in rows}
    assert indicators == {
        "unemployment_rate_pct_15_24", "unemployment_rate_pct_25_44",
        "unemployment_rate_pct_45_74", "unemployment_rate_pct_men",
        "unemployment_rate_pct_women",
    }
    assert all(r["value"] == 5.5 and r["source"] == "cbs" for r in rows)


@respx.mock
def test_population_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83474NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2025MM01", "BevolkingAanHetEindVanDePeriode_8": 17900000,
             "LevendGeborenKinderen_2": 13000, "Overledenen_3": 15000,
             "Immigratie_4": 12000, "EmigratieInclusiefAdministratieveC_5": 9000,
             "TotaleBevolkingsgroei_7": 4000},
        ]))
    )
    rows = nl._population_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["population_total"] == 17900000
    assert by_indicator["births"] == 13000
    assert by_indicator["deaths"] == 15000
    assert by_indicator["immigration"] == 12000
    assert by_indicator["emigration"] == 9000
    assert by_indicator["population_growth"] == 4000


@respx.mock
def test_birth_detail_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85722NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "1950JJ00", "GemiddeldKindertalPerVrouw_43": 3.097,
             "LevendGeborenKinderenRelatief_2": 22.7, "AlgemeenVruchtbaarheidscijfer_3": 90.5,
             "TotaalAlleKinderen_50": 30.6, "DoodgeborenKinderen28Relatief_34": 19.3},
        ]))
    )
    rows = nl._birth_detail_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["fertility_rate_children_per_woman"] == 3.097
    assert by_indicator["births_per_1000_pop"] == 22.7
    assert by_indicator["general_fertility_rate_per_1000"] == 90.5
    assert by_indicator["avg_mother_age_years"] == 30.6
    assert by_indicator["stillbirth_rate_per_1000"] == 19.3
    assert all(r["period_date"] == date(1950, 1, 1) for r in rows)


@respx.mock
def test_life_expectancy_rows_covers_all_genders_and_skips_rolling_windows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/37360ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "1861TM66", "Levensverwachting_4": None},
            {"Perioden": "1950JJ00", "Levensverwachting_4": 70.6},
        ]))
    )
    rows = nl._life_expectancy_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["life_expectancy_years_total"] == 70.6
    assert by_indicator["life_expectancy_years_men"] == 70.6
    assert by_indicator["life_expectancy_years_women"] == 70.6
    assert all(r["period_date"] == date(1950, 1, 1) for r in rows)  # rolling window dropped


@respx.mock
def test_producer_confidence_rows():
    respx.get(
        "https://opendata.cbs.nl/ODataApi/odata/81234ned/TypedDataSet",
        params={"$filter": "BedrijfstakkenBranchesSBI2008 eq '307500' and Marges eq 'MW00000' "
                           "and Seizoencorrectie eq 'A042500'"},
    ).mock(return_value=httpx.Response(200, json=cbs_json([
        {"Perioden": "2026MM08", "Producentenvertrouwen_1": 3.7},
    ])))
    rows = nl._producer_confidence_rows(_ctx())
    assert len(rows) == 1
    assert rows[0]["indicator"] == "producer_confidence_index"
    assert rows[0]["value"] == 3.7


@respx.mock
def test_consumer_confidence_rows():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83693NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2026MM07", "Consumentenvertrouwen_1": -35,
             "EconomischKlimaat_2": -59, "Koopbereidheid_3": -19},
        ]))
    )
    rows = nl._consumer_confidence_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["consumer_confidence_index"] == -35
    assert by_indicator["economic_climate_index"] == -59
    assert by_indicator["willingness_to_buy_index"] == -19


@respx.mock
def test_energy_production_rows_covers_all_sources():
    respx.get("https://opendata.cbs.nl/ODataApi/odata/86266NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([
            {"Perioden": "2024JJ00", "ElektriciteitGWh_2": 15000, "Elektriciteit_4": 12.5},
        ]))
    )
    rows = nl._energy_production_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    for name in nl.ENERGY_PRODUCTION_SOURCES.values():
        assert by_indicator[f"electricity_production_gwh_{name}"] == 15000
        assert by_indicator[f"electricity_share_pct_{name}"] == 12.5
    assert all(r["period_date"] == date(2024, 1, 1) for r in rows)


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
def test_bank_rate_rows_parses_all_three_mir_series():
    fixture = (FIXTURES / "nl_metrics_ecb_irs.csv").read_text()
    for key in nl.ECB_MIR_KEYS.values():
        respx.get(f"https://data-api.ecb.europa.eu/service/data/{key}").mock(
            return_value=httpx.Response(200, text=fixture)
        )
    rows = nl._bank_rate_rows(_ctx())
    indicators = {r["indicator"] for r in rows}
    assert indicators == {"bank_mortgage_rate_pct", "bank_savings_rate_pct",
                           "bank_term_deposit_rate_pct"}
    assert len(rows) == 9  # 3 series x 3 observations in the fixture
    assert all(r["source"] == "ecb" and r["unit"] == "%" for r in rows)


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
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85792NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85592NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/80590ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83474NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/85722NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/37360ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/81234ned/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/83693NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/86266NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    respx.get("https://opendata.cbs.nl/ODataApi/odata/82058NED/TypedDataSet").mock(
        return_value=httpx.Response(200, json=cbs_json([]))
    )
    fixture = (FIXTURES / "nl_metrics_ecb_irs.csv").read_text()
    respx.get("https://data-api.ecb.europa.eu/service/data/IRS/M.NL.L.L40.CI.0000.EUR.N.Z").mock(
        return_value=httpx.Response(200, text=fixture)
    )
    for key in nl.ECB_MIR_KEYS.values():
        respx.get(f"https://data-api.ecb.europa.eu/service/data/{key}").mock(
            return_value=httpx.Response(200, text=fixture)
        )
    result = nl.fetch(_ctx())
    table, rows = result[0]
    assert table == "price_index"
    indicators = {r["indicator"] for r in rows}
    assert "cpi_index" in indicators
    assert "gov_bond_10y_pct" in indicators


def _ctx():
    return nl.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

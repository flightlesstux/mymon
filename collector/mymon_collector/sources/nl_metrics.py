"""Netherlands-specific indicators: CBS (Statistics Netherlands) StatLine and the ECB.

Everything lands in ``price_index`` (PK ``period_date, country_iso3, indicator, source``),
``country_iso3='NLD'``. CBS's OData v3 API (``opendata.cbs.nl``) needs no key and each table
here is small (a few hundred rows), so every run re-pulls full history and there is no
separate backfill — same pattern as ``price_indices.py``.

CBS tables used (probed live 2026-09, table IDs are stable CBS identifiers):
- ``83131NED`` Consumentenprijzen (CPI): category ``T001112`` (all spending) for headline
  CPI + YoY inflation, ``CPI011000`` (Voedingsmiddelen) for food-only CPI, plus the index
  value (no YoY) for each of the 12 top-level COICOP spending categories (housing/energy,
  transport, health, education, ...) — a cost-of-living breakdown.
- ``85773NED`` Bestaande koopwoningen (existing home sales): price index, average sale
  price, month's transaction count.
- ``70675ned`` Huurverhoging woningen (annual rent increase, all landlords), 1959-present.
- ``85592NED`` Gemiddelde energietarieven (average consumer energy tariffs): gas
  (Euro/m3, columns 1-6) and electricity (Euro/kWh, columns 7-15) variable contract price,
  incl. VAT (``Btw='A048944'``).
- ``80590ned`` Arbeidsdeelname en werkloosheid: seasonally adjusted unemployment rate,
  total population 15-75 (``Geslacht='T001038'``, ``Leeftijd='52052'``).
- ``82058NED`` Logiesaccommodaties (tourism): total hotel/accommodation guests and
  overnight stays, all accommodation types.

ECB Data Portal, same SDMX CSV mechanism already used by ``reserves_ecb.py``:
- ``IRS`` dataflow: the Dutch 10-year government bond yield ("long-term interest rate for
  convergence purposes").
- ``MIR`` dataflow (MFI Interest Rate Statistics — what Dutch banks actually report to DNB,
  not a government proxy): the composite new-business mortgage rate, the overnight
  deposit/savings rate, and the term-deposit rate. (An earlier pass concluded bank rates
  "aren't freely available" from searching the DNB and CBS websites directly — that was
  wrong; ECB's MIR dataflow carries them, confirmed live against the 220 NL series it
  actually publishes.)

Netherlands-specific things that turned out NOT to be freely available (checked live,
2026-09): road traffic congestion (NDW's open data is a live DATEX II XML snapshot with no
historical query API; ANWB's traffic page is a JS-rendered app with no public API). Not
faked here.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "price_index"
REGION_TABLE = "region_metric"
COUNTRY = "NLD"

CBS_BASE = "https://opendata.cbs.nl/ODataApi/odata"
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
ECB_BOND_YIELD_KEY = "IRS/M.NL.L.L40.CI.0000.EUR.N.Z"

# ECB MIR (MFI Interest Rate Statistics) — what Dutch banks actually charge/pay, reported
# monthly via DNB. Confirmed live (2026-09) against the NL series list (220 series):
#   A2C = loans to households for house purchase, 'A' = annualised agreed rate (pure
#         interest, not APRC), new business composite across all maturities.
#   L22 = overnight deposits (households + non-financial corporations), i.e. ordinary
#         savings/current accounts.
#   L23 = deposits with agreed maturity (term deposits/savings).
ECB_MIR_KEYS: dict[str, str] = {
    "bank_mortgage_rate_pct": "MIR/M.NL.B.A2C.A.R.A.2250.EUR.N",
    "bank_savings_rate_pct": "MIR/M.NL.B.L22.A.R.A.2250.EUR.N",
    "bank_term_deposit_rate_pct": "MIR/M.NL.B.L23.A.R.A.2250.EUR.N",
}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _row(period: date, indicator: str, value: float, unit: str, source: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": COUNTRY,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": source,
    }


def _region_row(
    period: date, region_code: str, indicator: str, value: float, unit: str
) -> dict[str, Any]:
    return {
        "period_date": period,
        "region_code": region_code,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "cbs",
    }


def _cbs_period(value: str) -> date | None:
    """CBS months look like ``2025MM01``, quarters ``2025KW02``, years ``2025JJ00``."""
    s = (value or "").strip()
    if len(s) != 8:
        return None
    if s[4:6] == "KW":
        try:
            year, q = int(s[:4]), int(s[6:8])
        except ValueError:
            return None
        if q not in (1, 2, 3, 4):
            return None
        return date(year, (q - 1) * 3 + 1, 1)
    try:
        year = int(s[:4])
    except ValueError:
        return None
    if s[4:6] == "MM":
        try:
            return date(year, int(s[6:8]), 1)
        except ValueError:
            return None
    if s[4:6] == "JJ":
        return date(year, 1, 1)
    return None


def _cbs_get(ctx: Ctx, table: str, filt: str | None = None) -> list[dict[str, Any]]:
    url = f"{CBS_BASE}/{table}/TypedDataSet"
    params = {"$format": "json"}
    if filt:
        params["$filter"] = filt
    resp = ctx.http.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    value = data.get("value")
    if not isinstance(value, list):
        raise ValueError(f"CBS {table}: unexpected payload shape")
    return value


# --------------------------------------------------------------------------- CBS: CPI

# The 12 top-level COICOP spending categories CBS breaks the CPI into. Slugs are used
# directly as `price_index.indicator` (as `cpi_cat_<slug>`) and are readable enough to use
# as-is for a dashboard legend — no separate label lookup needed.
CPI_CATEGORIES: dict[str, str] = {
    "CPI010000": "food_and_drink",
    "CPI020000": "alcohol_and_tobacco",
    "CPI030000": "clothing_and_footwear",
    "CPI040000": "housing_water_energy",
    "CPI050000": "furnishings_household",
    "CPI060000": "health",
    "CPI070000": "transport",
    "CPI080000": "communication",
    "CPI090000": "recreation_and_culture",
    "CPI100000": "education",
    "CPI110000": "restaurants_and_hotels",
    "CPI120000": "misc_goods_and_services",
}

# Leaf-level (most granular) grocery/food product codes within 83131NED's food &
# non-alcoholic-drink division — the 6-digit codes one level below CPI_CATEGORIES'
# "food_and_drink" group total. Confirmed live against the full 408-entry
# Bestedingscategorieen dimension list (2026-09); these are the ones whose last two
# digits aren't "00", i.e. not themselves a subgroup total.
CPI_PRODUCTS: dict[str, str] = {
    "CPI011110": "rice", "CPI011120": "flour_and_other_grains", "CPI011130": "bread",
    "CPI011140": "other_bakery_products", "CPI011150": "pizza_and_quiche",
    "CPI011160": "pasta_and_couscous", "CPI011170": "breakfast_cereals",
    "CPI011180": "other_grain_products", "CPI011210": "beef_and_veal", "CPI011220": "pork",
    "CPI011230": "lamb_and_goat", "CPI011240": "poultry", "CPI011250": "other_meat",
    "CPI011270": "smoked_dried_salted_meat", "CPI011280": "other_meat_preparations",
    "CPI011310": "fresh_or_chilled_fish", "CPI011320": "frozen_fish",
    "CPI011330": "fresh_shellfish", "CPI011350": "smoked_dried_salted_fish",
    "CPI011360": "fish_preparations_and_preserves", "CPI011410": "fresh_whole_milk",
    "CPI011420": "fresh_semi_skimmed_milk", "CPI011430": "uht_milk", "CPI011440": "yoghurt",
    "CPI011450": "cheese_and_quark", "CPI011460": "other_dairy_products", "CPI011470": "eggs",
    "CPI011510": "butter", "CPI011520": "margarine_and_vegetable_fats",
    "CPI011530": "olive_oil", "CPI011540": "other_edible_oils", "CPI011610": "fresh_fruit",
    "CPI011630": "dried_fruit_and_nuts", "CPI011640": "fruit_preserves",
    "CPI011710": "fresh_vegetables", "CPI011720": "frozen_vegetables",
    "CPI011730": "dried_vegetables", "CPI011740": "potatoes", "CPI011750": "crisps",
    "CPI011810": "sugar", "CPI011820": "jam_and_honey", "CPI011830": "chocolate",
    "CPI011840": "sweets", "CPI011850": "ice_cream", "CPI011860": "artificial_sweeteners",
    "CPI011910": "sauces_and_dressings", "CPI011920": "salt_spices_and_herbs",
    "CPI011930": "baby_food", "CPI011940": "ready_meals", "CPI011990": "other_food_nec",
    "CPI012110": "coffee", "CPI012120": "tea", "CPI012130": "cocoa_powder",
    "CPI012210": "mineral_water", "CPI012220": "soft_drinks",
    "CPI012230": "fruit_and_vegetable_juices",
}


def _cpi_product_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, slug in CPI_PRODUCTS.items():
        recs = _cbs_get(ctx, "83131NED", f"Bestedingscategorieen eq '{code}'")
        for rec in recs:
            raw = rec.get("Perioden") or ""
            if raw[4:6] != "MM":
                continue  # see _cpi_rows — same table, same MM/JJ collision risk
            period = _cbs_period(raw)
            if period is None:
                continue
            idx = _num(rec.get("CPI_1"))
            if idx is not None:
                rows.append(_row(period, f"cpi_product_{slug}", idx, "2015=100", "cbs"))
            yoy = _num(rec.get("JaarmutatieCPI_5"))
            if yoy is not None:
                rows.append(_row(period, f"cpi_product_{slug}_yoy", yoy, "%", "cbs"))
    return rows


def _cpi_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # (CBS category code, index indicator name, YoY indicator name or None)
    headline = [
        ("T001112  ", "cpi_index", "cpi_inflation_pct"),
        ("CPI011000", "food_cpi_index", "food_cpi_inflation_pct"),
    ]
    categories = [(code, f"cpi_cat_{slug}", None) for code, slug in CPI_CATEGORIES.items()]
    for code, index_name, inflation_name in headline + categories:
        recs = _cbs_get(ctx, "83131NED", f"Bestedingscategorieen eq '{code}'")
        for rec in recs:
            raw = rec.get("Perioden") or ""
            if raw[4:6] != "MM":
                continue  # 83131NED also carries an annual (JJ00) rollup of the same
                # series; JJ00 maps to the same 1st-of-year date as MM01, so pulling
                # both would silently let one clobber the other via the upsert PK
            period = _cbs_period(raw)
            if period is None:
                continue
            idx = _num(rec.get("CPI_1"))
            if idx is not None:
                rows.append(_row(period, index_name, idx, "2015=100", "cbs"))
            if inflation_name:
                yoy = _num(rec.get("JaarmutatieCPI_5"))
                if yoy is not None:
                    rows.append(_row(period, inflation_name, yoy, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: rent


def _rent_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "70675ned"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        value = _num(rec.get("Huurverhoging_1"))
        if value is not None:
            rows.append(_row(period, "rent_increase_pct", value, "%", "cbs"))
    return rows


# ------------------------------------------------------------------- CBS: house prices, by province
#
# 85792NED breaks the house-price series down by region (RegioS): the 12 provinces
# (codes PV20-PV31), 4 landsdelen, the national total and 4 major cities. Only the 12
# provinces are kept — they match the `region` lookup table exactly, so no city/country
# rows leak into region_metric. Quarterly, not monthly, hence the 'KW' period format.


def _house_price_regional_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "85792NED"):
        region_code = (rec.get("RegioS") or "").strip()
        if not region_code.startswith("PV"):
            continue
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        idx = _num(rec.get("PrijsindexVerkoopprijzen_1"))
        if idx is not None:
            rows.append(_region_row(period, region_code, "house_price_index", idx, "2020=100"))
        avg = _num(rec.get("GemiddeldeVerkoopprijs_7"))
        if avg is not None:
            rows.append(_region_row(period, region_code, "house_price_avg_eur", avg, "EUR"))
        sold = _num(rec.get("VerkochteWoningen_4"))
        if sold is not None:
            rows.append(_region_row(period, region_code, "house_sales_count", sold, "count"))
    return rows


# --------------------------------------------------------------------------- CBS: house prices


def _house_price_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "85773NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        idx = _num(rec.get("PrijsindexVerkoopprijzen_1"))
        if idx is not None:
            rows.append(_row(period, "house_price_index", idx, "2020=100", "cbs"))
        avg = _num(rec.get("GemiddeldeVerkoopprijs_7"))
        if avg is not None:
            rows.append(_row(period, "house_price_avg_eur", avg, "EUR", "cbs"))
        sold = _num(rec.get("VerkochteWoningen_4"))
        if sold is not None:
            rows.append(_row(period, "house_sales_count", sold, "count", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: energy tariffs


def _energy_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "85592NED", "Btw eq 'A048944'"):  # incl. VAT
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        gas = _num(rec.get("VariabelLeveringstariefContractprijs_3"))
        if gas is not None:
            rows.append(_row(period, "gas_variable_price_eur_m3", gas, "EUR/m3", "cbs"))
        elec = _num(rec.get("VariabelLeveringstariefContractprijs_9"))
        if elec is not None:
            rows.append(_row(period, "electricity_variable_price_eur_kwh", elec, "EUR/kWh", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: unemployment


def _unemployment_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "Geslacht eq 'T001038' and Leeftijd eq '52052   '"
    for rec in _cbs_get(ctx, "80590ned", filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        rate = _num(rec.get("Seizoengecorrigeerd_8"))
        if rate is not None:
            rows.append(_row(period, "unemployment_rate_pct", rate, "%", "cbs"))
        participation = _num(rec.get("Seizoengecorrigeerd_14"))  # netto arbeidsparticipatie
        if participation is not None:
            rows.append(_row(period, "labour_participation_pct", participation, "%", "cbs"))
    return rows


# ------------------------------------------------------------- CBS: labour market, by age/gender
#
# Same table (80590ned) as unemployment above, just other Geslacht/Leeftijd combinations —
# CBS's fixed-width dimension codes need the exact padding these use, copied from a live
# probe of the Geslacht/Leeftijd dimension lists.

LABOUR_BREAKDOWN_DIMENSIONS: dict[str, tuple[str, str]] = {
    # indicator suffix -> (Geslacht code, Leeftijd code)
    "15_24": ("T001038", "53050   "),
    "25_44": ("T001038", "53310   "),
    "45_74": ("T001038", "53825   "),
    "men": ("3000   ", "52052   "),
    "women": ("4000   ", "52052   "),
}


def _labour_breakdown_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suffix, (gender, age) in LABOUR_BREAKDOWN_DIMENSIONS.items():
        filt = f"Geslacht eq '{gender}' and Leeftijd eq '{age}'"
        for rec in _cbs_get(ctx, "80590ned", filt):
            period = _cbs_period(rec.get("Perioden"))
            if period is None:
                continue
            rate = _num(rec.get("Seizoengecorrigeerd_8"))
            if rate is not None:
                rows.append(_row(period, f"unemployment_rate_pct_{suffix}", rate, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: population


def _population_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    columns = {
        "population_total": "BevolkingAanHetEindVanDePeriode_8",
        "births": "LevendGeborenKinderen_2",
        "deaths": "Overledenen_3",
        "immigration": "Immigratie_4",
        "emigration": "EmigratieInclusiefAdministratieveC_5",
        "population_growth": "TotaleBevolkingsgroei_7",
    }
    for rec in _cbs_get(ctx, "83474NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for indicator, col in columns.items():
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, "count", "cbs"))
    return rows


# ------------------------------------------------------------------ CBS: electricity production
#
# 86266NED breaks gross electricity production down by energy carrier — annual, not
# monthly, hence sparser than the rest of this module. CentraleDecentraleProductie codes
# aren't padded in this table (unlike Geslacht/Leeftijd above); confirmed via a live probe
# of both dimension lists.

ENERGY_PRODUCTION_SOURCES: dict[str, str] = {
    # Energiedragers code -> our indicator suffix
    "E006565": "renewable_total",
    "E006620": "nonrenewable_total",
    "E006589": "solar",
    "E006588": "wind",
    "E006560": "natural_gas",
    "E006461": "coal",
    "E006602": "nuclear",
    "E006566": "biomass",
}


def _energy_production_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, name in ENERGY_PRODUCTION_SOURCES.items():
        filt = f"CentraleDecentraleProductie eq 'E007022' and Energiedragers eq '{code}'"
        for rec in _cbs_get(ctx, "86266NED", filt):
            period = _cbs_period(rec.get("Perioden"))
            if period is None:
                continue
            gwh = _num(rec.get("ElektriciteitGWh_2"))
            if gwh is not None:
                rows.append(_row(period, f"electricity_production_gwh_{name}", gwh, "GWh", "cbs"))
            share = _num(rec.get("Elektriciteit_4"))
            if share is not None:
                rows.append(_row(period, f"electricity_share_pct_{name}", share, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: tourism


def _tourism_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "82058NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        guests = _num(rec.get("Totaal_1"))
        if guests is not None:
            rows.append(_row(period, "tourism_guests_thousands", guests, "x1000", "cbs"))
        stays = _num(rec.get("Totaal_4"))
        if stays is not None:
            rows.append(_row(period, "tourism_overnight_stays_thousands", stays, "x1000", "cbs"))
        occ = _num(rec.get("Bezettingsgraad_7"))
        if occ is not None:
            rows.append(_row(period, "tourism_occupancy_pct", occ, "%", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: births, detail
#
# 85722NED — annual key birth figures back to 1950, far deeper than the monthly headline
# count from 83474NED (1995+). No dimension filtering: one flat row per year.

BIRTH_DETAIL_COLUMNS: dict[str, str] = {
    "fertility_rate_children_per_woman": "GemiddeldKindertalPerVrouw_43",
    "births_per_1000_pop": "LevendGeborenKinderenRelatief_2",
    "general_fertility_rate_per_1000": "AlgemeenVruchtbaarheidscijfer_3",
    "avg_mother_age_years": "TotaalAlleKinderen_50",
    "stillbirth_rate_per_1000": "DoodgeborenKinderen28Relatief_34",
}


def _birth_detail_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "85722NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for indicator, col in BIRTH_DETAIL_COLUMNS.items():
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, "ratio", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: life expectancy
#
# 37360ned mixes annual (...JJ00) rows with rolling 5-year-window rows (e.g. "1861TM66");
# _cbs_period() only recognizes the JJ00 form, which conveniently drops the rolling-window
# rows for free and still leaves an unbroken annual series back to 1950.

LIFE_EXPECTANCY_GENDERS: dict[str, str] = {
    "T001038": "total",
    "3000   ": "men",
    "4000   ": "women",
}
LIFE_EXPECTANCY_AGE_ZERO = "10010"  # LeeftijdOp31December code for age 0 (at birth)


def _life_expectancy_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gender_code, suffix in LIFE_EXPECTANCY_GENDERS.items():
        filt = (
            f"LeeftijdOp31December eq '{LIFE_EXPECTANCY_AGE_ZERO}' "
            f"and Geslacht eq '{gender_code}'"
        )
        for rec in _cbs_get(ctx, "37360ned", filt):
            period = _cbs_period(rec.get("Perioden"))
            if period is None:
                continue
            years = _num(rec.get("Levensverwachting_4"))
            if years is not None:
                rows.append(_row(period, f"life_expectancy_years_{suffix}", years, "years", "cbs"))
    return rows


# ------------------------------------------------------------- CBS: producer confidence
#
# 81234ned — monthly producer confidence (industry sentiment), back to 1985. Industrie
# totaal (307500), value margin (MW00000, not the 95% CI bounds), seasonally adjusted
# (A042500, the only Seizoencorrectie value this table has).


def _producer_confidence_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = (
        "BedrijfstakkenBranchesSBI2008 eq '307500' and Marges eq 'MW00000' "
        "and Seizoencorrectie eq 'A042500'"
    )
    for rec in _cbs_get(ctx, "81234ned", filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        value = _num(rec.get("Producentenvertrouwen_1"))
        if value is not None:
            rows.append(_row(period, "producer_confidence_index", value, "index", "cbs"))
    return rows


# ------------------------------------------------------------- CBS: consumer confidence
#
# 83693NED — monthly consumer confidence, economic climate and willingness to buy, back
# to 1986. Flat table, single row per period, no dimension filtering needed.


def _consumer_confidence_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "83693NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        for col, indicator in (
            ("Consumentenvertrouwen_1", "consumer_confidence_index"),
            ("EconomischKlimaat_2", "economic_climate_index"),
            ("Koopbereidheid_3", "willingness_to_buy_index"),
        ):
            value = _num(rec.get(col))
            if value is not None:
                rows.append(_row(period, indicator, value, "index", "cbs"))
    return rows


# --------------------------------------------------------------------------- ECB: bond yield


def _ecb_series_rows(ctx: Ctx, key: str, indicator: str) -> list[dict[str, Any]]:
    """One ECB SDMX series (``dataflow/series-key``, e.g. ``IRS/M.NL...``) as monthly rows."""
    resp = ctx.http.get(f"{ECB_BASE}/{key}", params={"format": "csvdata"})
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "TIME_PERIOD" not in reader.fieldnames:
        raise ValueError(f"ECB {key} CSV missing columns, got {reader.fieldnames}")
    rows: list[dict[str, Any]] = []
    for rec in reader:
        period_str = (rec.get("TIME_PERIOD") or "").strip()
        try:
            year, month = period_str.split("-")
            period = date(int(year), int(month), 1)
        except (ValueError, TypeError):
            continue
        value = _num(rec.get("OBS_VALUE"))
        if value is None:
            continue
        rows.append(_row(period, indicator, value, "%", "ecb"))
    return rows


def _bond_yield_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _ecb_series_rows(ctx, ECB_BOND_YIELD_KEY, "gov_bond_10y_pct")


def _bank_rate_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for indicator, key in ECB_MIR_KEYS.items():
        rows.extend(_ecb_series_rows(ctx, key, indicator))
    return rows


# --------------------------------------------------------------------------- source


def _dedupe(rows: list[dict[str, Any]], key_field: str) -> list[dict[str, Any]]:
    seen: dict[tuple, dict] = {}
    for r in rows:
        seen[(r["period_date"], r[key_field], r["indicator"], r["source"])] = r
    return list(seen.values())


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("nl_metrics: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("nl_metrics: %s returned no rows", name)
            failures += 1
            continue
        log.info("nl_metrics: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    country_rows, country_failures = _run_upstreams(ctx, (
        ("cpi", _cpi_rows),
        ("cpi_products", _cpi_product_rows),
        ("rent", _rent_rows),
        ("house_prices", _house_price_rows),
        ("energy", _energy_rows),
        ("unemployment", _unemployment_rows),
        ("labour_breakdown", _labour_breakdown_rows),
        ("population", _population_rows),
        ("birth_detail", _birth_detail_rows),
        ("life_expectancy", _life_expectancy_rows),
        ("producer_confidence", _producer_confidence_rows),
        ("consumer_confidence", _consumer_confidence_rows),
        ("energy_production", _energy_production_rows),
        ("tourism", _tourism_rows),
        ("bond_yield", _bond_yield_rows),
        ("bank_rates", _bank_rate_rows),
    ))
    region_rows, region_failures = _run_upstreams(ctx, (
        ("house_prices_regional", _house_price_regional_rows),
    ))
    if not country_rows and not region_rows:
        raise RuntimeError("nl_metrics: every upstream failed")
    log.info("nl_metrics: %d country rows (%d failures), %d region rows (%d failures)",
              len(country_rows), country_failures, len(region_rows), region_failures)
    return [
        (TABLE, _dedupe(country_rows, "country_iso3")),
        (REGION_TABLE, _dedupe(region_rows, "region_code")),
    ]


SOURCE = Source(
    name="nl_metrics",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE, REGION_TABLE],
    description=(
        "Netherlands: CBS CPI/food CPI, house prices (national + by province), energy "
        "tariffs and production mix, unemployment (headline + age/gender breakdown), "
        "population, births/fertility/life expectancy detail back to 1950, producer and "
        "consumer confidence, tourism, plus the ECB's Dutch 10-year government bond "
        "yield and MIR bank interest rates."
    ),
)

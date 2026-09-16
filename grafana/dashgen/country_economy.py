"""One dashboard generator, six countries — Germany, Italy, Spain, Greece, Turkey and
France all share the same eurostat_metrics indicators, so this loops instead of six
near-identical nl_economy.py-style files. Tier-1 depth (CPI, unemployment, population,
demographics, house prices, confidence) matching the first pass of the NL folder;
ports/agriculture/construction/vehicle-style depth lands in their own shared modules.
"""

import _lib
from _lib import CAT, dashboard, stat, timeseries, write

COUNTRIES = [
    ("DE", "DEU", "Germany", True),
    ("IT", "ITA", "Italy", True),
    ("ES", "ESP", "Spain", True),
    ("GR", "GRC", "Greece", True),
    ("TR", "TUR", "Turkey", False),  # not in the euro area, no ECB bond/bank rate data
    ("FR", "FRA", "France", True),
]

RANGE_START = "2000-01-01"


def q(country_iso3: str, indicator: str, source: str = "eurostat") -> str:
    return (
        f"SELECT period_date AS time, value FROM price_index "
        f"WHERE country_iso3='{country_iso3}' AND indicator='{indicator}' AND source='{source}' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


def q_latest(country_iso3: str, indicator: str, source: str = "eurostat") -> str:
    return (
        f"SELECT value FROM price_index WHERE country_iso3='{country_iso3}' "
        f"AND indicator='{indicator}' AND source='{source}' ORDER BY period_date DESC LIMIT 1"
    )


def q_multi(country_iso3: str, indicators: list[str], source: str = "eurostat") -> str:
    inlist = ",".join(f"'{i}'" for i in indicators)
    return (
        f"SELECT period_date AS time, indicator AS metric, value FROM price_index "
        f"WHERE country_iso3='{country_iso3}' AND indicator IN ({inlist}) AND source='{source}' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


for code, iso3, name, has_ecb_rates in COUNTRIES:
    _lib._id = 0  # stable panel ids per dashboard, matching generate_all.py's own reset

    inflation = q_multi(iso3, ["cpi_inflation_pct", "food_cpi_inflation_pct"])
    demographics = q_multi(iso3, ["births", "deaths"])
    confidence = q_multi(iso3, ["consumer_confidence_index", "producer_confidence_index"])

    panels = [
        stat("CPI inflation, YoY", 0, 0, 4, 4, q_latest(iso3, "cpi_inflation_pct"),
             unit="percent", decimals=1, color=CAT[1]),
        stat("Food inflation, YoY", 4, 0, 4, 4, q_latest(iso3, "food_cpi_inflation_pct"),
             unit="percent", decimals=1, color=CAT[3]),
        stat("Unemployment", 8, 0, 4, 4, q_latest(iso3, "unemployment_rate_pct"),
             unit="percent", decimals=1, color=CAT[2]),
        stat("House price index", 12, 0, 4, 4, q_latest(iso3, "house_price_index"),
             decimals=1, color=CAT[0]),
        stat("Population", 16, 0, 4, 4, q_latest(iso3, "population_total"),
             unit="short", decimals=0, color=CAT[6]),
        stat("Consumer confidence", 20, 0, 4, 4, q_latest(iso3, "consumer_confidence_index"),
             decimals=1, color=CAT[5]),

        timeseries("Consumer Price Index (2015=100)", 0, 4, 12, 9, q(iso3, "cpi_index"),
                   decimals=1, colors={"value": CAT[0]}, fill=15),
        timeseries("CPI inflation, year-on-year", 12, 4, 12, 9, inflation, unit="percent",
                   decimals=1, colors={"cpi_inflation_pct": CAT[0],
                                        "food_cpi_inflation_pct": CAT[3]}, fill=0),

        timeseries("Unemployment rate", 0, 13, 12, 9, q(iso3, "unemployment_rate_pct"),
                   unit="percent", decimals=1, colors={"value": CAT[2]}, fill=15),
        timeseries("House price index (2015=100)", 12, 13, 12, 9, q(iso3, "house_price_index"),
                   decimals=1, colors={"value": CAT[0]}, fill=15,
                   description="Quarterly. Not every quarter is published for every "
                               "country at the same lag."),

        timeseries("Population", 0, 22, 12, 9, q(iso3, "population_total"), unit="short",
                   decimals=0, colors={"value": CAT[6]}, fill=15,
                   description="Annual, 1 January each year."),
        timeseries("Births vs. deaths, per year", 12, 22, 12, 9, demographics, unit="short",
                   decimals=0, colors={"births": CAT[2], "deaths": CAT[7]}, fill=0),

        timeseries("Net migration, per year", 0, 31, 12, 9, q(iso3, "net_migration"),
                   unit="short", decimals=0, colors={"value": CAT[6]}, fill=15, points=True,
                   description="Eurostat's net migration plus statistical adjustment."),
        timeseries("Consumer vs. producer confidence", 12, 31, 12, 9, confidence, decimals=1,
                   colors={"consumer_confidence_index": CAT[5],
                           "producer_confidence_index": CAT[4]}, fill=0, points=True),

        stat("Life expectancy at birth", 0, 40, 6, 4, q_latest(iso3, "life_expectancy_years_total"),
             unit="short", decimals=1, color=CAT[6]),
        stat("Fertility rate, children/woman", 6, 40, 6, 4,
             q_latest(iso3, "fertility_rate_children_per_woman"), decimals=2, color=CAT[4]),
        stat("Avg. age of mother at childbirth", 12, 40, 6, 4,
             q_latest(iso3, "avg_mother_age_years"), unit="short", decimals=1, color=CAT[1]),
        stat("Net migration, latest year", 18, 40, 6, 4, q_latest(iso3, "net_migration"),
             unit="short", decimals=0, color=CAT[6]),

        timeseries("Life expectancy at birth, by gender", 0, 44, 12, 9,
                   q_multi(iso3, ["life_expectancy_years_men", "life_expectancy_years_women"]),
                   unit="short", decimals=1,
                   colors={"life_expectancy_years_men": CAT[0],
                           "life_expectancy_years_women": CAT[4]}, fill=0,
                   description="Eurostat demo_mlexpec, annual."),
        timeseries("Total fertility rate", 12, 44, 12, 9,
                   q(iso3, "fertility_rate_children_per_woman"), decimals=3,
                   colors={"value": CAT[4]}, fill=15,
                   description="Eurostat demo_find, annual. 2.1 is roughly the "
                               "replacement rate."),
    ]

    if has_ecb_rates:
        bank_rates = q_multi(iso3, ["bank_mortgage_rate_pct", "bank_savings_rate_pct",
                                     "bank_term_deposit_rate_pct"], "ecb")
        panels += [
            stat("10y govt bond yield", 0, 53, 6, 4, q_latest(iso3, "gov_bond_10y_pct", "ecb"),
                 unit="percent", decimals=2, color=CAT[6]),
            stat("Bank mortgage rate", 6, 53, 6, 4,
                 q_latest(iso3, "bank_mortgage_rate_pct", "ecb"), unit="percent", decimals=2,
                 color=CAT[1]),
            stat("Bank savings rate", 12, 53, 6, 4,
                 q_latest(iso3, "bank_savings_rate_pct", "ecb"), unit="percent", decimals=2,
                 color=CAT[2]),
            stat("Bank term deposit rate", 18, 53, 6, 4,
                 q_latest(iso3, "bank_term_deposit_rate_pct", "ecb"), unit="percent",
                 decimals=2, color=CAT[3]),

            timeseries("10-year government bond yield", 0, 57, 12, 9,
                       q(iso3, "gov_bond_10y_pct", "ecb"), unit="percent", decimals=2,
                       colors={"value": CAT[6]}, fill=15,
                       description="ECB long-term interest rate for convergence purposes."),
            timeseries("Bank interest rates (what banks actually report to the ECB)",
                       12, 57, 12, 9, bank_rates, unit="percent", decimals=2,
                       colors={"bank_mortgage_rate_pct": CAT[1],
                               "bank_savings_rate_pct": CAT[2],
                               "bank_term_deposit_rate_pct": CAT[3]}, fill=0,
                       description="ECB MIR statistics — new-business mortgage rate "
                                   "vs. what banks pay on savings and term deposits. "
                                   "Not government bond yields."),
        ]

    write(dashboard(f"{code.lower()}-economy", f"{name}: Economy & Population", panels,
                    [name.lower()], refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name}: CPI/food inflation, unemployment, house prices, "
                                f"population and demographics, life expectancy, "
                                f"fertility, consumer/producer confidence"
                                + (", government bond yield and bank interest rates"
                                   if has_ecb_rates else "")
                                + f" — via Eurostat{' and ECB' if has_ecb_rates else ''}, "
                                  f"since 2000 where the data goes back that far."),
          f"{code}/{code.lower()}-economy")

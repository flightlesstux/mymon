"""One dashboard generator, six countries — government debt/deficit, minimum wage and
trade (exports/imports), all from eurostat_finance.py. None of these existed on any
country dashboard before.
"""

import _lib
from _lib import CAT, dashboard, stat, timeseries, write

COUNTRIES = [
    ("DE", "DEU", "Germany", True, True),
    ("IT", "ITA", "Italy", True, False),
    ("ES", "ESP", "Spain", True, True),
    ("GR", "GRC", "Greece", True, True),
    ("TR", "TUR", "Turkey", False, True),
    ("FR", "FRA", "France", True, True),
]
# (code, iso3, name, has_govt_finance, has_minimum_wage — Turkey isn't in Eurostat's
# ESA2010 government finance framework; Italy has no statutory minimum wage.)

RANGE_START = "2000-01-01"


def q(country_iso3: str, indicator: str) -> str:
    return (
        f"SELECT period_date AS time, value FROM price_index "
        f"WHERE country_iso3='{country_iso3}' AND indicator='{indicator}' AND source='eurostat' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


def q_latest(country_iso3: str, indicator: str) -> str:
    return (
        f"SELECT value FROM price_index WHERE country_iso3='{country_iso3}' "
        f"AND indicator='{indicator}' AND source='eurostat' ORDER BY period_date DESC LIMIT 1"
    )


def q_multi(country_iso3: str, indicators: list[str]) -> str:
    inlist = ",".join(f"'{i}'" for i in indicators)
    return (
        f"SELECT period_date AS time, indicator AS metric, value FROM price_index "
        f"WHERE country_iso3='{country_iso3}' AND indicator IN ({inlist}) AND source='eurostat' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


for code, iso3, name, has_govt_finance, has_minimum_wage in COUNTRIES:
    _lib._id = 0

    trade = q_multi(iso3, ["exports_goods_services_meur", "imports_goods_services_meur"])

    panels = [
        stat("Exports, latest year (million EUR)", 0, 0, 12, 4,
             q_latest(iso3, "exports_goods_services_meur"), unit="short", decimals=0,
             color=CAT[2]),
        stat("Imports, latest year (million EUR)", 12, 0, 12, 4,
             q_latest(iso3, "imports_goods_services_meur"), unit="short", decimals=0,
             color=CAT[7]),

        timeseries("Goods & services trade: exports vs. imports (million EUR)", 0, 4, 24, 10,
                   trade, unit="short", decimals=0,
                   colors={"exports_goods_services_meur": CAT[2],
                           "imports_goods_services_meur": CAT[7]}, fill=0,
                   description="Eurostat nama_10_gdp, current prices, annual since "
                               "1975 where available. Goods and services combined, "
                               "not split out."),
    ]

    if has_govt_finance:
        panels += [
            stat("Government debt, % of GDP", 0, 14, 12, 4,
                 q_latest(iso3, "govt_debt_pct_gdp"), unit="percent", decimals=1,
                 color=CAT[3]),
            stat("Government deficit(-)/surplus(+), % of GDP", 12, 14, 12, 4,
                 q_latest(iso3, "govt_deficit_pct_gdp"), unit="percent", decimals=1,
                 color=CAT[4]),
            timeseries("Government debt, % of GDP", 0, 18, 12, 9,
                       q(iso3, "govt_debt_pct_gdp"), unit="percent", decimals=1,
                       colors={"value": CAT[3]}, fill=15,
                       description="General government (S13), ESA2010 consolidated "
                                   "gross debt. Annual, back to 1995 where available."),
            timeseries("Government deficit(-)/surplus(+), % of GDP", 12, 18, 12, 9,
                       q(iso3, "govt_deficit_pct_gdp"), unit="percent", decimals=1,
                       colors={"value": CAT[4]}, fill=15,
                       description="Net lending(+)/borrowing(-), general government."),
        ]

    if has_minimum_wage:
        panels += [
            stat("Statutory minimum wage, EUR/month", 0, 27, 24, 4,
                 q_latest(iso3, "minimum_wage_eur_month"), unit="currencyEUR",
                 decimals=0, color=CAT[0]),
            timeseries("Statutory minimum wage over time (EUR/month)", 0, 31, 24, 9,
                       q(iso3, "minimum_wage_eur_month"), unit="currencyEUR", decimals=0,
                       colors={"value": CAT[0]}, fill=15,
                       description="Eurostat earn_mw_cur, half-yearly since 1999."),
        ]

    write(dashboard(f"{code.lower()}-finance", f"{name}: Public Finance & Trade", panels,
                    [name.lower()], refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name}: goods & services trade"
                                + (", government debt/deficit" if has_govt_finance else "")
                                + (", statutory minimum wage" if has_minimum_wage else "")
                                + " — via Eurostat."),
          f"{code}/{code.lower()}-finance")

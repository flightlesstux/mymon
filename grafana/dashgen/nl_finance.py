"""NL: Public Finance & Trade — government debt/deficit, minimum wage and goods+services
trade, from eurostat_finance.py. Mirrors country_finance.py's DE/IT/ES/GR/TR/FR
dashboards; the Netherlands gets the same Eurostat-sourced data here since none of these
three topics has an NL-specific (CBS) source in this project.
"""

from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

TRADE = nl_multi(["exports_goods_services_meur", "imports_goods_services_meur"], "eurostat")

panels = [
    stat("Exports, latest year (million EUR)", 0, 0, 12, 4,
         nl_latest("exports_goods_services_meur", "eurostat"), unit="short", decimals=0,
         color=CAT[2]),
    stat("Imports, latest year (million EUR)", 12, 0, 12, 4,
         nl_latest("imports_goods_services_meur", "eurostat"), unit="short", decimals=0,
         color=CAT[7]),

    timeseries("Goods & services trade: exports vs. imports (million EUR)", 0, 4, 24, 10,
               TRADE, unit="short", decimals=0,
               colors={"exports_goods_services_meur": CAT[2],
                       "imports_goods_services_meur": CAT[7]}, fill=0,
               description="Eurostat nama_10_gdp, current prices, annual since 1975 "
                           "where available."),

    stat("Government debt, % of GDP", 0, 14, 12, 4,
         nl_latest("govt_debt_pct_gdp", "eurostat"), unit="percent", decimals=1, color=CAT[3]),
    stat("Government deficit(-)/surplus(+), % of GDP", 12, 14, 12, 4,
         nl_latest("govt_deficit_pct_gdp", "eurostat"), unit="percent", decimals=1, color=CAT[4]),
    timeseries("Government debt, % of GDP", 0, 18, 12, 9,
               nl("govt_debt_pct_gdp", "eurostat"), unit="percent", decimals=1,
               colors={"value": CAT[3]}, fill=15,
               description="General government (S13), ESA2010 consolidated gross "
                           "debt. Annual, back to 1995 where available."),
    timeseries("Government deficit(-)/surplus(+), % of GDP", 12, 18, 12, 9,
               nl("govt_deficit_pct_gdp", "eurostat"), unit="percent", decimals=1,
               colors={"value": CAT[4]}, fill=15,
               description="Net lending(+)/borrowing(-), general government."),

    stat("Statutory minimum wage, EUR/month", 0, 27, 24, 4,
         nl_latest("minimum_wage_eur_month", "eurostat"), unit="currencyEUR", decimals=0,
         color=CAT[0]),
    timeseries("Statutory minimum wage over time (EUR/month)", 0, 31, 24, 9,
               nl("minimum_wage_eur_month", "eurostat"), unit="currencyEUR", decimals=0,
               colors={"value": CAT[0]}, fill=15,
               description="Eurostat earn_mw_cur, half-yearly since 1999."),
]

write(dashboard("nl-finance", "NL: Public Finance & Trade", panels, ["netherlands"],
                refresh="1h", time_from="2000-01-01T00:00:00Z",
                description="Dutch government debt/deficit, statutory minimum wage and "
                            "goods & services trade — via Eurostat (no CBS source "
                            "covers these three topics)."),
      "NL/nl-finance")

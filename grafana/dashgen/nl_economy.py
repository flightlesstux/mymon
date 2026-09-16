from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

CPI_YOY = nl_multi(["cpi_inflation_pct", "food_cpi_inflation_pct"], "cbs")
FX_EUR_USD = """
SELECT ts AS time, 1/rate AS "EUR/USD" FROM fx_rate
WHERE base='USD' AND quote='EUR' AND source='frankfurter' AND ts >= '2025-01-01' AND $__timeFilter(ts)
ORDER BY 1
"""
FX_EUR_TRY = """
SELECT ts AS time, rate AS "EUR/TRY" FROM fx_rate
WHERE base='EUR' AND quote='TRY' AND source='tcmb' AND ts >= '2025-01-01' AND $__timeFilter(ts)
ORDER BY 1
"""

panels = [
    stat("CPI inflation, YoY", 0, 0, 4, 4, nl_latest("cpi_inflation_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[1]),
    stat("Food inflation, YoY", 4, 0, 4, 4, nl_latest("food_cpi_inflation_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[3]),
    stat("Unemployment", 8, 0, 4, 4, nl_latest("unemployment_rate_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[2]),
    stat("10y govt bond yield", 12, 0, 4, 4, nl_latest("gov_bond_10y_pct", "ecb"),
         unit="percent", decimals=2, color=CAT[6]),
    stat("EUR/USD", 16, 0, 4, 4,
         "SELECT ts AS time, 1/rate AS value FROM fx_rate WHERE base='USD' AND quote='EUR' "
         "AND source='frankfurter' AND ts > now() - interval '30 days' ORDER BY ts",
         decimals=4, color=CAT[0]),
    stat("EUR/TRY", 20, 0, 4, 4,
         "SELECT ts AS time, rate AS value FROM fx_rate WHERE base='EUR' AND quote='TRY' "
         "AND source='tcmb' AND ts > now() - interval '30 days' ORDER BY ts",
         decimals=2, color=CAT[7]),

    timeseries("Consumer Price Index (2015=100)", 0, 4, 12, 9, nl("cpi_index", "cbs"),
               decimals=1, colors={"value": CAT[0]}, fill=15),
    timeseries("CPI inflation, year-on-year", 12, 4, 12, 9, CPI_YOY, unit="percent", decimals=1,
               colors={"cpi_inflation_pct": CAT[0], "food_cpi_inflation_pct": CAT[3]}, fill=0),

    timeseries("Unemployment rate, seasonally adjusted", 0, 13, 12, 9,
               nl("unemployment_rate_pct", "cbs"), unit="percent", decimals=1,
               colors={"value": CAT[2]}, fill=15),
    timeseries("10-year government bond yield", 12, 13, 12, 9, nl("gov_bond_10y_pct", "ecb"),
               unit="percent", decimals=2, colors={"value": CAT[6]}, fill=15,
               description="ECB long-term interest rate for convergence purposes."),

    timeseries("FX: EUR/USD", 0, 22, 12, 9, FX_EUR_USD, unit="none", decimals=4,
               colors={"EUR/USD": CAT[0]}, fill=0,
               description="EUR/USD and EUR/TRY are on separate panels — TRY's scale "
                           "(50+) would flatten USD's (~1.15) on one shared axis."),
    timeseries("FX: EUR/TRY", 12, 22, 12, 9, FX_EUR_TRY, unit="none", decimals=2,
               colors={"EUR/TRY": CAT[7]}, fill=0),

    stat("NS active train disruptions", 0, 31, 12, 4,
         "SELECT period_date AS time, value FROM price_index WHERE country_iso3='NLD' "
         "AND indicator='ns_disruptions_active' AND source='ns' "
         "ORDER BY period_date DESC LIMIT 1",
         decimals=0, color=CAT[1],
         description="Live-only (no historical API); shows 'No data' until NS_API_KEY is "
                     "set — free instant signup at apiportal.ns.nl."),
    stat("...of which unplanned (STORING)", 12, 31, 12, 4,
         "SELECT period_date AS time, value FROM price_index WHERE country_iso3='NLD' "
         "AND indicator='ns_disruptions_unplanned' AND source='ns' "
         "ORDER BY period_date DESC LIMIT 1",
         decimals=0, color=CAT[7]),
]

write(dashboard("nl-economy", "NL: Economy & Rates", panels, ["netherlands"],
                refresh="1h", time_from="2025-01-01T00:00:00Z",
                description="Inflation, unemployment, the 10-year government bond yield "
                            "and FX for the Netherlands, since 2025."),
      "NL/nl-economy")

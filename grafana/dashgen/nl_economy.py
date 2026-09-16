from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

CPI_YOY = nl_multi(["cpi_inflation_pct", "food_cpi_inflation_pct"], "cbs")
BANK_RATES = nl_multi(
    ["bank_mortgage_rate_pct", "bank_savings_rate_pct", "bank_term_deposit_rate_pct"], "ecb"
)
FX_EUR_USD = """
SELECT ts AS time, 1/rate AS "EUR/USD" FROM fx_rate
WHERE base='USD' AND quote='EUR' AND source='frankfurter' AND ts >= '2000-01-01' AND $__timeFilter(ts)
ORDER BY 1
"""
FX_EUR_TRY = """
SELECT ts AS time, rate AS "EUR/TRY" FROM fx_rate
WHERE base='EUR' AND quote='TRY' AND source='tcmb' AND ts >= '2000-01-01' AND $__timeFilter(ts)
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

    stat("Bank mortgage rate", 0, 31, 8, 4, nl_latest("bank_mortgage_rate_pct", "ecb"),
         unit="percent", decimals=2, color=CAT[1],
         description="New-business composite rate on loans for house purchase, all Dutch "
                     "banks (ECB MIR statistics, reported via DNB)."),
    stat("Bank savings rate", 8, 31, 8, 4, nl_latest("bank_savings_rate_pct", "ecb"),
         unit="percent", decimals=2, color=CAT[2],
         description="Overnight deposit rate (ordinary savings/current accounts)."),
    stat("Bank term deposit rate", 16, 31, 8, 4, nl_latest("bank_term_deposit_rate_pct", "ecb"),
         unit="percent", decimals=2, color=CAT[3]),

    timeseries("Bank interest rates (what Dutch banks actually report to DNB)", 0, 35, 24, 9,
               BANK_RATES, unit="percent", decimals=2,
               colors={"bank_mortgage_rate_pct": CAT[1], "bank_savings_rate_pct": CAT[2],
                       "bank_term_deposit_rate_pct": CAT[3]}, fill=0,
               description="ECB MIR statistics — new-business mortgage rate vs. what banks "
                           "pay on savings and term deposits. Not government bond yields."),
]

write(dashboard("nl-economy", "NL: Economy & Rates", panels, ["netherlands"],
                refresh="1h", time_from="2000-01-01T00:00:00Z",
                description="Inflation, unemployment, the government bond yield, actual "
                            "Dutch bank interest rates and FX, since 2000, where the data goes back that far."),
      "NL/nl-economy")

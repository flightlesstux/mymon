from _lib import CAT, dashboard, barchart, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

ENERGY = nl_multi(["gas_variable_price_eur_m3", "electricity_variable_price_eur_kwh"], "cbs")

panels = [
    stat("House price index", 0, 0, 5, 4, nl_latest("house_price_index", "cbs"),
         decimals=1, color=CAT[0]),
    stat("Average sale price", 5, 0, 5, 4, nl_latest("house_price_avg_eur", "cbs"),
         unit="currencyEUR", decimals=0, color=CAT[0]),
    stat("Gas, incl. VAT", 10, 0, 4, 4, nl_latest("gas_variable_price_eur_m3", "cbs"),
         unit="currencyEUR", decimals=3, color=CAT[1]),
    stat("Electricity, incl. VAT", 14, 0, 4, 4,
         nl_latest("electricity_variable_price_eur_kwh", "cbs"),
         unit="currencyEUR", decimals=3, color=CAT[3]),
    stat("Rent increase, latest year", 18, 0, 6, 4, nl_latest("rent_increase_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[6],
         description="Annual figure (CBS publishes this yearly, not monthly)."),

    timeseries("Existing home price index (2020=100)", 0, 4, 12, 9,
               nl("house_price_index", "cbs"), decimals=1, colors={"value": CAT[0]}, fill=15),
    timeseries("Average sale price", 12, 4, 12, 9, nl("house_price_avg_eur", "cbs"),
               unit="currencyEUR", decimals=0, colors={"value": CAT[0]}, fill=15),

    barchart("Home sales per month", 0, 13, 12, 9, nl("house_sales_count", "cbs"),
             unit="short", color=CAT[2], horizontal=False),
    timeseries("Annual rent increase, all landlords", 12, 13, 12, 9,
               nl("rent_increase_pct", "cbs"), unit="percent", decimals=1,
               colors={"value": CAT[6]}, fill=15, points=True,
               description="CBS publishes this once a year."),

    timeseries("Energy tariffs, incl. VAT (variable contract price)", 0, 22, 24, 9, ENERGY,
               decimals=3, colors={"gas_variable_price_eur_m3": CAT[1],
                                    "electricity_variable_price_eur_kwh": CAT[3]}, fill=0,
               legend="right",
               description="Gas in EUR/m3, electricity in EUR/kWh — different units on one "
                           "axis, use the legend."),
]

write(dashboard("nl-housing-energy", "NL: Housing & Energy", panels, ["netherlands"],
                refresh="1h", time_from="2025-01-01T00:00:00Z",
                description="Dutch existing-home prices, sales volume, rent increases and "
                            "consumer energy tariffs, since 2025."),
      "NL/nl-housing-energy")

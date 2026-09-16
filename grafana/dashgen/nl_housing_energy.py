from _lib import CAT, dashboard, barchart, geomap, marker_layer, stat, target, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

ENERGY = nl_multi(["gas_variable_price_eur_m3", "electricity_variable_price_eur_kwh"], "cbs")

REGIONAL_LATEST = """
SELECT DISTINCT ON (m.region_code) r.name AS "Province", r.lat, r.lon,
       m.value AS "Avg price EUR", m.period_date AS "Quarter"
FROM region_metric m JOIN region r ON r.code = m.region_code
WHERE m.indicator='house_price_avg_eur' AND m.source='cbs'
ORDER BY m.region_code, m.period_date DESC
"""

REGIONAL_BAR = """
SELECT r.name AS "Province", m.value AS "Avg sale price EUR"
FROM region_metric m JOIN region r ON r.code = m.region_code
WHERE m.indicator='house_price_avg_eur' AND m.source='cbs'
  AND m.period_date = (SELECT max(period_date) FROM region_metric
                        WHERE indicator='house_price_avg_eur' AND source='cbs')
ORDER BY m.value DESC
"""

REGIONAL_INDEX_TREND = """
SELECT m.period_date AS time, r.name AS metric, m.value
FROM region_metric m JOIN region r ON r.code = m.region_code
WHERE m.indicator='house_price_index' AND m.source='cbs' AND $__timeFilter(m.period_date)
ORDER BY 1
"""

# The 12 provinces, in the same order region_metric_lookup returns them — a fixed color per
# province so it stays stable between the trend legend and (if added later) any other panel
# that lists the same 12 names.
_PROVINCES = ["Groningen", "Fryslân", "Drenthe", "Overijssel", "Flevoland", "Gelderland",
              "Utrecht", "Noord-Holland", "Zuid-Holland", "Zeeland", "Noord-Brabant", "Limburg"]
PROVINCE_COLORS = {name: CAT[i % len(CAT)] for i, name in enumerate(_PROVINCES)}

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

    geomap("Average sale price by province, latest quarter", 0, 22, 14, 13,
           [marker_layer("Provinces", "A", size_field="Avg price EUR",
                         color_field="Avg price EUR", size=(10, 32),
                         color_scheme="continuous-BlPu", opacity=0.85, text_field="Province")],
           targets=[target(REGIONAL_LATEST, "A", "table")],
           view={"id": "coords", "lat": 52.1, "lon": 5.4, "zoom": 6.8, "allLayers": True},
           description="CBS 85792NED, house prices by province — one country-level number "
                       "can't show that Utrecht and Fryslân aren't the same market."),
    barchart("Average sale price by province, ranked", 14, 22, 10, 13, REGIONAL_BAR,
             unit="currencyEUR", color=CAT[0]),

    timeseries("Price index by province (2020=100)", 0, 35, 24, 10, REGIONAL_INDEX_TREND,
               decimals=1, colors=PROVINCE_COLORS, fill=0, legend="right",
               description="All 12 provinces — quarterly, so this fills in more slowly "
                           "than the monthly national panels above."),

    timeseries("Energy tariffs, incl. VAT (variable contract price)", 0, 45, 24, 9, ENERGY,
               decimals=3, colors={"gas_variable_price_eur_m3": CAT[1],
                                    "electricity_variable_price_eur_kwh": CAT[3]}, fill=0,
               legend="right",
               description="Gas in EUR/m3, electricity in EUR/kWh — different units on one "
                           "axis, use the legend."),
]

write(dashboard("nl-housing-energy", "NL: Housing & Energy", panels, ["netherlands"],
                refresh="1h", time_from="2000-01-01T00:00:00Z",
                description="Dutch existing-home prices (national and by province), sales "
                            "volume, rent increases and consumer energy tariffs, since 2000 "
                            "where the data goes back that far."),
      "NL/nl-housing-energy")

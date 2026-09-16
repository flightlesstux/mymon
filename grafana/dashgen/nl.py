from _lib import CAT, STATUS, dashboard, geomap, marker_layer, stat, table, target, \
    timeseries, barchart, text, write

NL_CITIES = ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"]
CITY_LIST_SQL = ",".join(f"'{c}'" for c in NL_CITIES)
RANGE_FROM = "2025-01-01T00:00:00Z"

# ------------------------------------------------------------------------- helpers


def nl(indicator: str, source: str | None = None, col_time="period_date AS time", extra="") -> str:
    src = f"AND source='{source}' " if source else ""
    return (
        f"SELECT {col_time}, value FROM price_index "
        f"WHERE country_iso3='NLD' AND indicator='{indicator}' {src}"
        f"AND period_date >= '2025-01-01' AND $__timeFilter(period_date) {extra} ORDER BY 1"
    )


def nl_latest(indicator: str, source: str | None = None) -> str:
    src = f"AND source='{source}' " if source else ""
    return (
        f"SELECT value FROM price_index WHERE country_iso3='NLD' AND indicator='{indicator}' "
        f"{src}ORDER BY period_date DESC LIMIT 1"
    )


# ------------------------------------------------------------------------- queries

CITY_NOW = f"""
SELECT DISTINCT ON (w.city)
  w.city AS "City", c.lat, c.lon, w.temp_c AS "Temp °C", w.humidity AS "Humidity %",
  w.wind_kph AS "Wind km/h", w.aqi_eu AS "AQI", w.ts AS "Observed"
FROM weather_current w JOIN city c ON c.city = w.city
WHERE w.city IN ({CITY_LIST_SQL}) AND w.ts > now() - interval '3 hours'
ORDER BY w.city, w.ts DESC
"""

CITY_TEMP_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, avg(temp_c) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_FROM}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

CITY_AQI_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, avg(aqi_eu) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_FROM}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

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

CPI_SQL = f"""
SELECT period_date AS time, value FROM price_index
WHERE country_iso3='NLD' AND indicator='cpi_index' AND source='cbs'
  AND period_date >= '2025-01-01' AND $__timeFilter(period_date) ORDER BY 1
"""
CPI_YOY_SQL = f"""
SELECT period_date AS time, indicator AS metric, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ('cpi_inflation_pct', 'food_cpi_inflation_pct')
  AND period_date >= '2025-01-01' AND $__timeFilter(period_date) ORDER BY 1
"""
FOOD_CPI_SQL = nl("food_cpi_index", "cbs")
HOUSE_PRICE_IDX = nl("house_price_index", "cbs")
HOUSE_PRICE_AVG = nl("house_price_avg_eur", "cbs")
HOUSE_SALES = nl("house_sales_count", "cbs")
ENERGY_SQL = f"""
SELECT period_date AS time, indicator AS metric, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ('gas_variable_price_eur_m3', 'electricity_variable_price_eur_kwh')
  AND period_date >= '2025-01-01' AND $__timeFilter(period_date) ORDER BY 1
"""
UNEMPLOYMENT_SQL = nl("unemployment_rate_pct", "cbs")
BOND_YIELD_SQL = nl("gov_bond_10y_pct", "ecb")
TOURISM_SQL = f"""
SELECT period_date AS time, indicator AS metric, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ('tourism_guests_thousands', 'tourism_overnight_stays_thousands')
  AND period_date >= '2025-01-01' AND $__timeFilter(period_date) ORDER BY 1
"""
TOURISM_OCC_SQL = nl("tourism_occupancy_pct", "cbs")

# ------------------------------------------------------------------------- panels

map_targets = [target(CITY_NOW, "cities", "table")]
layers = [
    marker_layer("Cities (temperature)", "cities", color_field="Temp °C", size=(14, 14),
                 color_scheme="continuous-BlYlRd", min_=-5, max_=30, opacity=0.95, text_field="City"),
]

panels = [
    stat("CPI inflation, YoY", 0, 0, 4, 4, nl_latest("cpi_inflation_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[1]),
    stat("Food inflation, YoY", 4, 0, 4, 4, nl_latest("food_cpi_inflation_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[3]),
    stat("House price index", 8, 0, 4, 4, nl_latest("house_price_index", "cbs"),
         decimals=1, color=CAT[0]),
    stat("Unemployment", 12, 0, 4, 4, nl_latest("unemployment_rate_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[2]),
    stat("10y govt bond yield", 16, 0, 4, 4, nl_latest("gov_bond_10y_pct", "ecb"),
         unit="percent", decimals=2, color=CAT[6]),
    stat("EUR/USD", 20, 0, 4, 4,
         "SELECT ts AS time, 1/rate AS value FROM fx_rate WHERE base='USD' AND quote='EUR' "
         "AND source='frankfurter' AND ts > now() - interval '30 days' ORDER BY ts",
         decimals=4, color=CAT[0]),

    geomap("Netherlands — 5 cities, current temperature", 0, 4, 24, 13, layers,
           view={"id": "coords", "lat": 52.1, "lon": 5.1, "zoom": 7.3, "allLayers": True},
           targets=map_targets,
           description="Amsterdam, Rotterdam, The Hague, Utrecht, Eindhoven — latest reading."),

    timeseries("City temperatures, daily average since Jan 2025", 0, 17, 12, 9, CITY_TEMP_TREND,
               unit="celsius", decimals=1, fill=0,
               colors={"Amsterdam": CAT[0], "Rotterdam": CAT[1], "The Hague": CAT[2],
                       "Utrecht": CAT[3], "Eindhoven": CAT[4]}, legend="right"),
    timeseries("Air quality (European AQI), daily average", 12, 17, 12, 9, CITY_AQI_TREND,
               decimals=0, fill=0,
               colors={"Amsterdam": CAT[0], "Rotterdam": CAT[1], "The Hague": CAT[2],
                       "Utrecht": CAT[3], "Eindhoven": CAT[4]}, legend="right"),

    timeseries("Consumer Price Index (2015=100)", 0, 26, 12, 9, CPI_SQL, decimals=1,
               colors={"value": CAT[0]}, fill=15),
    timeseries("CPI inflation, year-on-year", 12, 26, 12, 9, CPI_YOY_SQL, unit="percent", decimals=1,
               colors={"cpi_inflation_pct": CAT[0], "food_cpi_inflation_pct": CAT[3]}, fill=0),

    timeseries("Food CPI (2015=100)", 0, 35, 12, 9, FOOD_CPI_SQL, decimals=1,
               colors={"value": CAT[3]}, fill=15),
    barchart("Home sales per month", 12, 35, 12, 9, HOUSE_SALES, unit="short", color=CAT[2],
             horizontal=False),

    timeseries("Existing home price index (2020=100)", 0, 44, 12, 9, HOUSE_PRICE_IDX, decimals=1,
               colors={"value": CAT[6]}, fill=15),
    timeseries("Average sale price", 12, 44, 12, 9, HOUSE_PRICE_AVG, unit="currencyEUR", decimals=0,
               colors={"value": CAT[6]}, fill=15),

    timeseries("Energy tariffs, incl. VAT (variable contract price)", 0, 53, 12, 9, ENERGY_SQL,
               decimals=3, colors={"gas_variable_price_eur_m3": CAT[1],
                                    "electricity_variable_price_eur_kwh": CAT[3]}, fill=0,
               description="Gas in EUR/m3, electricity in EUR/kWh — different units on one axis, use the legend."),
    timeseries("Unemployment rate, seasonally adjusted", 12, 53, 12, 9, UNEMPLOYMENT_SQL,
               unit="percent", decimals=1, colors={"value": CAT[2]}, fill=15),

    timeseries("10-year government bond yield", 0, 62, 12, 9, BOND_YIELD_SQL, unit="percent",
               decimals=2, colors={"value": CAT[6]}, fill=15,
               description="ECB long-term interest rate for convergence purposes."),
    timeseries("FX: EUR/USD", 12, 62, 6, 9, FX_EUR_USD, unit="none", decimals=4,
               colors={"EUR/USD": CAT[0]}, fill=0,
               description="EUR/USD and EUR/TRY are split into two panels — TRY's scale "
                           "(50+) would flatten USD's (~1.15) on one shared axis."),
    timeseries("FX: EUR/TRY", 18, 62, 6, 9, FX_EUR_TRY, unit="none", decimals=2,
               colors={"EUR/TRY": CAT[7]}, fill=0),

    timeseries("Tourism: guests and overnight stays (thousands)", 0, 71, 12, 9, TOURISM_SQL,
               unit="short", decimals=0,
               colors={"tourism_guests_thousands": CAT[0],
                       "tourism_overnight_stays_thousands": CAT[4]}, fill=0),
    timeseries("Hotel occupancy rate", 12, 71, 12, 9, TOURISM_OCC_SQL, unit="percent", decimals=1,
               colors={"value": CAT[4]}, fill=15),

    text("About this dashboard", 0, 80, 24, 5, f"""
**Sources:** CBS (Statistics Netherlands) StatLine open data — CPI, food CPI, house prices,
energy tariffs, unemployment, tourism. ECB Data Portal — 10-year government bond yield.
Frankfurter/TCMB — FX. Open-Meteo — weather and air quality for {", ".join(NL_CITIES)}.
All free, no API key. Data from 2025-01-01 onward where available; CBS monthly series lag
by a few weeks to a few months, which is normal for official statistics, not missing data.

**Not included, checked and found unavailable for free:** road traffic congestion (NDW's
open data is a live snapshot only, no historical query API; no public API found for ANWB
either) and current mortgage/deposit interest rates (no free NL-specific API found).
"""),
]

write(dashboard("nl", "Netherlands", panels, ["mymon", "netherlands"], refresh="1h",
                time_from="2025-01-01T00:00:00Z",
                description="Netherlands deep dive: inflation, food prices, housing, energy, "
                            "unemployment, interest rates, FX, tourism and weather since 2025."),
      "nl")

from _lib import CAT, dashboard, geomap, marker_layer, stat, table, target, timeseries, barchart, write

EU_LATEST = """
SELECT DISTINCT ON (f.country_iso2, f.fuel_type)
  c.name AS "Country", f.country_iso2 AS iso2, f.fuel_type AS fuel, f.price AS "EUR/L", c.lat, c.lon, f.period_date AS "Week"
FROM fuel_price f JOIN country_centroid c ON c.iso2 = f.country_iso2
WHERE f.source='eu_wob' AND f.fuel_type='${fuel}'
ORDER BY f.country_iso2, f.fuel_type, f.period_date DESC
"""
EU_BARS = """
SELECT c.name AS "Country", f.price AS "EUR/L"
FROM (
  SELECT DISTINCT ON (country_iso2) country_iso2, price FROM fuel_price
  WHERE source='eu_wob' AND fuel_type='${fuel}' ORDER BY country_iso2, period_date DESC
) f JOIN country_centroid c ON c.iso2 = f.country_iso2
ORDER BY f.price DESC
"""
EU_TREND = """
SELECT period_date AS time, country_iso2 AS metric, price AS value
FROM fuel_price WHERE source='eu_wob' AND fuel_type='${fuel}' AND country_iso2 IN ('DE','FR','NL','IT','ES','PL','GR') AND $__timeFilter(period_date)
ORDER BY 1
"""
EU_AVG = """
SELECT period_date AS time, fuel_type AS metric, avg(price) AS value
FROM fuel_price WHERE source='eu_wob' AND $__timeFilter(period_date) GROUP BY 1, 2 ORDER BY 1
"""
TR_NOW = """
SELECT DISTINCT ON (region, fuel_type) region AS "Province", fuel_type AS "Fuel", price AS "TRY/L", period_date AS "Date"
FROM fuel_price WHERE country_iso2='TR' ORDER BY region, fuel_type, period_date DESC
"""
TR_TREND = """
SELECT period_date AS time, fuel_type AS metric, price AS value
FROM fuel_price WHERE country_iso2='TR' AND region IN ('Istanbul','İstanbul','Istanbul (Avrupa)') AND $__timeFilter(period_date) ORDER BY 1
"""
TR_IN_EUR = """
SELECT f.period_date AS time, f.fuel_type AS metric, f.price / x.rate AS value
FROM fuel_price f
JOIN LATERAL (SELECT rate FROM fx_rate WHERE base='EUR' AND quote='TRY' AND source='tcmb' AND ts <= f.period_date + interval '1 day' ORDER BY ts DESC LIMIT 1) x ON true
WHERE f.country_iso2='TR' AND f.region IN ('Istanbul','İstanbul','Istanbul (Avrupa)') AND $__timeFilter(f.period_date) ORDER BY 1
"""
US_FUEL = """
SELECT period_date AS time, fuel_type AS metric, price AS value
FROM fuel_price WHERE source='eia' AND $__timeFilter(period_date) ORDER BY 1
"""
def pink(commodities, label_map=None):
    inlist = ",".join(f"'{c}'" for c in commodities)
    return f"""SELECT period_date AS time, commodity AS metric, price AS value
FROM commodity_price WHERE source='wb_pink' AND commodity IN ({inlist}) AND $__timeFilter(period_date) ORDER BY 1"""

def pink_indexed(commodities):
    inlist = ",".join(f"'{c}'" for c in commodities)
    return f"""WITH b AS (
  SELECT commodity, price AS p0 FROM commodity_price
  WHERE source='wb_pink' AND commodity IN ({inlist})
    AND period_date = (SELECT min(period_date) FROM commodity_price WHERE source='wb_pink' AND $__timeFilter(period_date))
)
SELECT c.period_date AS time, c.commodity AS metric, 100 * c.price / b.p0 AS value
FROM commodity_price c JOIN b ON b.commodity = c.commodity
WHERE c.source='wb_pink' AND c.commodity IN ({inlist}) AND $__timeFilter(c.period_date) ORDER BY 1"""

PINK_LATEST = """
SELECT commodity AS "Commodity", price AS "Price", unit AS "Unit", period_date AS "Month",
  round(100 * (price / NULLIF(lag12, 0) - 1), 1) AS "YoY %"
FROM (
  SELECT commodity, price, unit, period_date,
         lag(price, 12) OVER (PARTITION BY commodity ORDER BY period_date) AS lag12,
         row_number() OVER (PARTITION BY commodity ORDER BY period_date DESC) AS rn
  FROM commodity_price WHERE source='wb_pink'
) t WHERE rn = 1 ORDER BY commodity
"""
BIGMAC = """
SELECT c.name AS "Country", p.value AS "Big Mac USD"
FROM (SELECT DISTINCT ON (country_iso3) country_iso3, value FROM price_index WHERE indicator='bigmac_usd' ORDER BY country_iso3, period_date DESC) p
JOIN country_centroid c ON c.iso3 = p.country_iso3
ORDER BY p.value DESC
"""
BIGMAC_TREND = """
SELECT period_date AS time, country_iso3 AS metric, value
FROM price_index WHERE indicator='bigmac_usd' AND country_iso3 IN ('USA','TUR','DEU','GBR','JPN','CHN','BRA','CHE') AND $__timeFilter(period_date) ORDER BY 1
"""
FAO = """
SELECT period_date AS time, replace(indicator, 'fao_', '') AS metric, value
FROM price_index WHERE source='fao' AND $__timeFilter(period_date) ORDER BY 1
"""
INFLATION_MAP = """
SELECT DISTINCT ON (p.country_iso3) c.name AS "Country", p.value AS "Inflation %", c.lat, c.lon, p.period_date AS "Year"
FROM price_index p JOIN country_centroid c ON c.iso3 = p.country_iso3
WHERE p.indicator='cpi_inflation_pct' AND p.value IS NOT NULL AND p.country_iso3 NOT IN ('WLD','EMU')
ORDER BY p.country_iso3, p.period_date DESC
"""
INFLATION_TOP = """
SELECT c.name AS "Country", p.value AS "Inflation %"
FROM (SELECT DISTINCT ON (country_iso3) country_iso3, value, period_date FROM price_index WHERE indicator='cpi_inflation_pct' AND value IS NOT NULL ORDER BY country_iso3, period_date DESC) p
JOIN country_centroid c ON c.iso3 = p.country_iso3
WHERE p.period_date >= now() - interval '3 years' AND p.country_iso3 NOT IN ('WLD','EMU')
ORDER BY p.value DESC LIMIT 15
"""
INFLATION_TREND = """
SELECT period_date AS time, country_iso3 AS metric, value
FROM price_index WHERE indicator='cpi_inflation_pct' AND country_iso3 IN ('TUR','USA','EMU','GBR','DEU','JPN','ARG','BRA') AND $__timeFilter(period_date) ORDER BY 1
"""
ELEC = """
SELECT period_date AS time, country_iso3 AS metric, value
FROM price_index WHERE indicator='electricity_household_eur_kwh' AND country_iso3 IN ('DEU','NLD','ITA','ESP','FRA','POL','TUR','EUU') AND $__timeFilter(period_date) ORDER BY 1
"""
GAS = """
SELECT period_date AS time, country_iso3 AS metric, value
FROM price_index WHERE indicator='gas_household_eur_kwh' AND country_iso3 IN ('DEU','NLD','ITA','ESP','FRA','POL','TUR','EUU') AND $__timeFilter(period_date) ORDER BY 1
"""
ELEC_LATEST = """
SELECT c.name AS "Country", p.value AS "EUR/kWh"
FROM (SELECT DISTINCT ON (country_iso3) country_iso3, value FROM price_index WHERE indicator='electricity_household_eur_kwh' ORDER BY country_iso3, period_date DESC) p
JOIN country_centroid c ON c.iso3 = p.country_iso3 ORDER BY p.value DESC
"""
POLICY = """
SELECT period_date AS time, country_iso3 AS metric, value
FROM price_index WHERE indicator='policy_rate_pct' AND country_iso3 IN ('TUR','USA','EMU','GBR','JPN','BRA','CHN','RUS') AND $__timeFilter(period_date) ORDER BY 1
"""

FUEL_VAR = {
    "name": "fuel", "label": "Fuel", "type": "custom", "query": "petrol95 : Petrol 95,diesel : Diesel",
    "current": {"text": "Petrol 95", "value": "petrol95"}, "options": [
        {"text": "Petrol 95", "value": "petrol95", "selected": True}, {"text": "Diesel", "value": "diesel", "selected": False}],
    "multi": False, "includeAll": False, "hide": 0,
}

panels = [
    geomap("EU pump price, ${fuel} incl. taxes (Weekly Oil Bulletin)", 0, 0, 14, 13,
           [marker_layer("Price", "A", size_field="EUR/L", color_field="EUR/L", size=(8, 22), color_scheme="continuous-YlRd", min_=1.2, max_=2.2, opacity=0.85, text_field="iso2")],
           targets=[target(EU_LATEST, "A", "table")],
           view={"id": "coords", "lat": 52, "lon": 12, "zoom": 3.4, "allLayers": True}),
    barchart("EU ${fuel}, EUR per litre", 14, 0, 10, 13, EU_BARS, unit="currencyEUR", decimals=3, color=CAT[1]),
    timeseries("EU ${fuel}, selected countries", 0, 13, 12, 9, EU_TREND, unit="currencyEUR", decimals=3,
               colors={"DE": CAT[0], "FR": CAT[1], "NL": CAT[2], "IT": CAT[3], "ES": CAT[4],
                       "PL": CAT[5], "GR": CAT[6]}, fill=0),
    timeseries("EU average, petrol 95 vs diesel", 12, 13, 12, 9, EU_AVG, unit="currencyEUR", decimals=3, colors={"petrol95": CAT[3], "diesel": CAT[0]}, fill=0),

    table("Türkiye pump prices", 0, 22, 8, 9, TR_NOW, sort=("Province", False),
          overrides=[{"matcher": {"id": "byName", "options": "TRY/L"}, "properties": [{"id": "unit", "value": "currencyTRY"}, {"id": "decimals", "value": 2}]}]),
    timeseries("Istanbul pump prices, TRY/L", 8, 22, 8, 9, TR_TREND, unit="currencyTRY", decimals=2,
               colors={"petrol95": CAT[3], "diesel": CAT[0], "lpg": CAT[2]}, fill=0),
    timeseries("Istanbul pump prices in EUR/L (TCMB rate)", 16, 22, 8, 9, TR_IN_EUR, unit="currencyEUR", decimals=3,
               colors={"petrol95": CAT[3], "diesel": CAT[0], "lpg": CAT[2]}, fill=0,
               description="Comparable with the EU map above."),
    timeseries("United States retail gasoline and diesel, USD/gal (EIA)", 0, 31, 12, 8, US_FUEL, unit="currencyUSD", decimals=3,
               colors={"petrol_regular": CAT[3], "diesel": CAT[0]}, fill=0,
               description="Shown once EIA_API_KEY is configured."),
    timeseries("Natural gas — Europe, US, Japan LNG (World Bank Pink Sheet, USD/MMBtu)", 12, 31, 12, 8,
               pink(["natural_gas_europe", "natural_gas_us", "liquefied_natural_gas_japan"]), unit="currencyUSD",
               decimals=2,
               colors={"natural_gas_europe": CAT[0], "natural_gas_us": CAT[1],
                       "liquefied_natural_gas_japan": CAT[2]}, fill=0),

    timeseries("Energy — crude oil average, coal, natural gas index (Pink Sheet)", 0, 39, 12, 9,
               pink(["crude_oil_average", "coal_australian", "natural_gas_index"]), decimals=1,
               colors={"crude_oil_average": CAT[2], "coal_australian": CAT[7], "natural_gas_index": CAT[0]},
               fill=0,
               description="Units differ per series (USD/bbl, USD/mt, index)."),
    timeseries("Food staples indexed to 100 at range start — wheat, rice, maize, sugar, coffee, cocoa", 12, 39, 12, 9,
               pink_indexed(["wheat_us_hrw", "rice_thai_5", "maize", "sugar_world", "coffee_arabica", "cocoa"]),
               decimals=0,
               colors={"wheat_us_hrw": CAT[0], "rice_thai_5": CAT[1], "maize": CAT[2],
                       "sugar_world": CAT[3], "coffee_arabica": CAT[4], "cocoa": CAT[5]},
               fill=0, legend="right"),
    timeseries("Metals indexed to 100 — gold, silver, copper, aluminum, nickel, iron ore", 0, 48, 12, 9,
               pink_indexed(["gold", "silver", "copper", "aluminum", "nickel", "iron_ore_cfr_spot"]), decimals=0,
               colors={"gold": CAT[0], "silver": CAT[1], "copper": CAT[2], "aluminum": CAT[3],
                       "nickel": CAT[4], "iron_ore_cfr_spot": CAT[5]},
               fill=0, legend="right"),
    timeseries("Fertilizers — urea, DAP, potassium chloride (USD/mt)", 12, 48, 12, 9,
               pink(["urea", "dap", "potassium_chloride"]), unit="currencyUSD", decimals=0,
               colors={"urea": CAT[2], "dap": CAT[3], "potassium_chloride": CAT[6]}, fill=0),
    table("Pink Sheet, latest month, all commodities", 0, 57, 24, 11, PINK_LATEST, sort=("Commodity", False),
          overrides=[{"matcher": {"id": "byName", "options": "YoY %"},
                      "properties": [{"id": "unit", "value": "percent"},
                                     {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                                     {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "#0ca30c", "value": None}, {"color": "#d03b3b", "value": 0}]}},
                                     {"id": "color", "value": {"mode": "thresholds"}}]},
                     {"matcher": {"id": "byName", "options": "Month"}, "properties": [{"id": "unit", "value": "dateTimeAsIsoNoDateIfToday"}]}]),

    timeseries("FAO food price indices (2014-16 = 100)", 0, 68, 12, 9, FAO, decimals=0,
               colors={"food_index": CAT[0], "meat": CAT[1], "dairy": CAT[2], "cereals": CAT[3],
                       "oils": CAT[4], "sugar": CAT[5]}, fill=0, legend="right"),
    timeseries("Big Mac price in USD, selected countries (The Economist)", 12, 68, 12, 9, BIGMAC_TREND, unit="currencyUSD", decimals=2,
               colors={"USA": CAT[0], "TUR": CAT[1], "DEU": CAT[2], "GBR": CAT[3], "JPN": CAT[4],
                       "CHN": CAT[5], "BRA": CAT[6], "CHE": CAT[7]}, fill=0, legend="right"),
    barchart("Big Mac price in USD, latest", 0, 77, 8, 13, BIGMAC, unit="currencyUSD", decimals=2, color=CAT[3]),
    geomap("Consumer price inflation, latest year (World Bank)", 8, 77, 16, 13,
           [marker_layer("Inflation", "A", size_field="Inflation %", color_field="Inflation %", size=(4, 28), color_scheme="continuous-YlRd", min_=0, max_=30, opacity=0.7)],
           targets=[target(INFLATION_MAP, "A", "table")],
           view={"id": "zero", "lat": 25, "lon": 15, "zoom": 1.5, "allLayers": True}),
    barchart("Highest inflation, latest year", 0, 90, 8, 10, INFLATION_TOP, unit="percent", decimals=1, color=CAT[7]),
    timeseries("Inflation, selected countries", 8, 90, 16, 10, INFLATION_TREND, unit="percent", decimals=1,
               colors={"TUR": CAT[0], "USA": CAT[1], "EMU": CAT[2], "GBR": CAT[3], "DEU": CAT[4],
                       "JPN": CAT[5], "ARG": CAT[6], "BRA": CAT[7]}, fill=0, legend="right"),

    timeseries("Household electricity, EUR/kWh incl. taxes (Eurostat, semi-annual)", 0, 100, 8, 9, ELEC, decimals=3,
               colors={"DEU": CAT[0], "NLD": CAT[1], "ITA": CAT[2], "ESP": CAT[3], "FRA": CAT[4],
                       "POL": CAT[5], "TUR": CAT[6], "EUU": CAT[7]}, fill=0),
    timeseries("Household gas, EUR/kWh incl. taxes (Eurostat)", 8, 100, 8, 9, GAS, decimals=3,
               colors={"DEU": CAT[0], "NLD": CAT[1], "ITA": CAT[2], "ESP": CAT[3], "FRA": CAT[4],
                       "POL": CAT[5], "TUR": CAT[6], "EUU": CAT[7]}, fill=0),
    barchart("Household electricity, latest, EUR/kWh", 16, 100, 8, 9, ELEC_LATEST, decimals=3, color=CAT[3]),
    timeseries("Central bank policy rates (BIS / FRED)", 0, 109, 24, 9, POLICY, unit="percent", decimals=2,
               colors={"TUR": CAT[0], "USA": CAT[1], "EMU": CAT[2], "GBR": CAT[3], "JPN": CAT[4],
                       "BRA": CAT[5], "CHN": CAT[6], "RUS": CAT[7]}, fill=0, legend="right"),
]

write(dashboard("fuel-prices", "Fuel & Prices", panels, ["mymon", "prices"], refresh="1h", time_from="now-5y",
                templating=[FUEL_VAR],
                description="Pump prices across Europe and Türkiye, natural gas, commodities, food, Big Mac index, inflation, household energy prices."),
      "fuel-prices")

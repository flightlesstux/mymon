from _lib import CAT, dashboard, geomap, marker_layer, stat, table, target, timeseries, barchart, write

LATEST_WB = """
SELECT DISTINCT ON (r.country_iso3)
  r.country AS "Country", r.value_usd AS "Reserves USD", c.lat, c.lon, r.period_date AS "As of"
FROM reserves r JOIN country_centroid c ON c.iso3 = r.country_iso3
WHERE r.metric = 'total' AND r.source = 'worldbank' AND r.value_usd IS NOT NULL
  AND r.country_iso3 NOT IN ('WLD','EMU')
ORDER BY r.country_iso3, r.period_date DESC
"""

TOP15 = """
SELECT country AS "Country", value_usd AS "Total reserves"
FROM (
  SELECT DISTINCT ON (country_iso3) country, value_usd
  FROM reserves
  WHERE metric='total' AND source='worldbank' AND value_usd IS NOT NULL AND country_iso3 NOT IN ('WLD','EMU')
  ORDER BY country_iso3, period_date DESC
) t ORDER BY value_usd DESC LIMIT 15
"""

def wb_series(iso3, metric="total"):
    return f"""SELECT period_date AS time, value_usd AS "{iso3}" FROM reserves
WHERE country_iso3='{iso3}' AND metric='{metric}' AND source='worldbank' AND $__timeFilter(period_date) ORDER BY 1"""

TREND = """
SELECT period_date AS time, country AS metric, value_usd AS value
FROM reserves
WHERE metric='total' AND source='worldbank' AND country_iso3 IN ('CHN','JPN','CHE','IND','RUS','SAU','USA','TUR','KOR','BRA')
  AND $__timeFilter(period_date)
ORDER BY 1
"""

TR_WEEKLY = """
SELECT period_date AS time, metric, value_usd AS value
FROM reserves
WHERE country_iso3='TUR' AND source LIKE 'tcmb%%' AND metric IN ('gross_fx','gold','total') AND $__timeFilter(period_date)
ORDER BY 1
"""

TR_ANNUAL = """
SELECT period_date AS time, metric, value_usd AS value
FROM reserves
WHERE country_iso3='TUR' AND source='worldbank' AND metric IN ('total','gold','ex_gold') AND $__timeFilter(period_date)
ORDER BY 1
"""

US_ANNUAL = """
SELECT period_date AS time, metric, value_usd AS value
FROM reserves
WHERE country_iso3='USA' AND source='worldbank' AND metric IN ('total','gold','ex_gold') AND $__timeFilter(period_date)
ORDER BY 1
"""

US_MONTHLY = """
SELECT period_date AS time, value_usd AS "US reserves ex gold (FRED)"
FROM reserves WHERE country_iso3='USA' AND source='fred' AND metric='ex_gold' AND $__timeFilter(period_date) ORDER BY 1
"""

EA_MONTHLY = """
SELECT period_date AS time, value_usd AS value, source AS metric
FROM reserves WHERE country_iso3='EMU' AND source LIKE 'ecb%%' AND metric='total' AND $__timeFilter(period_date) ORDER BY 1
"""

EA_ANNUAL = """
SELECT period_date AS time, metric, value_usd AS value
FROM reserves WHERE country_iso3='EMU' AND source='worldbank' AND metric IN ('total','gold','ex_gold') AND $__timeFilter(period_date) ORDER BY 1
"""

GOLD_SHARE = """
SELECT country AS "Country", round(100 * gold / NULLIF(total,0), 1) AS "Gold share %"
FROM (
  SELECT DISTINCT ON (country_iso3) country_iso3, country, period_date,
    max(value_usd) FILTER (WHERE metric='gold') OVER w AS gold,
    max(value_usd) FILTER (WHERE metric='total') OVER w AS total
  FROM reserves
  WHERE source='worldbank' AND country_iso3 IN ('USA','DEU','ITA','FRA','RUS','CHN','CHE','JPN','IND','NLD','TUR','GBR','SAU','KOR','BRA')
  WINDOW w AS (PARTITION BY country_iso3, period_date)
  ORDER BY country_iso3, period_date DESC
) t WHERE total > 0 ORDER BY 2 DESC
"""

def latest_stat(iso3, label):
    return stat(label, 0, 0, 4, 4, f"""SELECT value_usd FROM reserves WHERE country_iso3='{iso3}' AND metric='total' AND source='worldbank' AND value_usd IS NOT NULL ORDER BY period_date DESC LIMIT 1""",
                unit="currencyUSD", decimals=0)

panels = []
x = 0
for iso3, label, color in [("CHN", "China", CAT[0]), ("JPN", "Japan", CAT[1]), ("CHE", "Switzerland", CAT[2]),
                           ("USA", "United States", CAT[3]), ("EMU", "Euro area", CAT[4]), ("TUR", "Türkiye", CAT[7])]:
    p = latest_stat(iso3, f"{label} — total reserves")
    p["gridPos"].update({"x": x, "y": 0, "w": 4, "h": 4})
    p["fieldConfig"]["defaults"]["color"] = {"mode": "fixed", "fixedColor": color}
    p["fieldConfig"]["defaults"]["thresholds"]["steps"][0]["color"] = color
    p["options"]["graphMode"] = "none"
    panels.append(p)
    x += 4

panels += [
    geomap("Total reserves incl. gold by country (World Bank, latest year)", 0, 4, 16, 14,
           [marker_layer("Reserves", "A", size_field="Reserves USD", color_field="Reserves USD", size=(4, 40),
                         color_scheme="continuous-BlPu", opacity=0.7, text_field=None)],
           view={"id": "zero", "lat": 30, "lon": 20, "zoom": 1.5, "allLayers": True},
           targets=[target(LATEST_WB, "A", "table")],
           description="Bubble size and colour = total reserves in USD. Source: World Bank FI.RES.TOTL.CD (annual)."),
    barchart("Top 15 reserve holders", 16, 4, 8, 14, TOP15, unit="currencyUSD", color=CAT[0]),
    timeseries("Total reserves, selected countries (annual, USD)", 0, 18, 24, 10, TREND, unit="currencyUSD", fill=0,
               colors={"China": CAT[0], "Japan": CAT[1], "Switzerland": CAT[2], "India": CAT[3],
                       "Russian Federation": CAT[4], "Saudi Arabia": CAT[5], "United States": CAT[6],
                       "Turkiye": CAT[7], "Korea, Rep.": CAT[0], "Brazil": CAT[1]},
               legend="right"),
    timeseries("Türkiye — weekly gross FX, gold and total (TCMB)", 0, 28, 12, 9, TR_WEEKLY, unit="currencyUSD", fill=10,
               colors={"gross_fx": CAT[0], "gold": CAT[3], "total": CAT[7]},
               description="Shown once EVDS_API_KEY is configured; otherwise empty."),
    timeseries("Türkiye — annual reserves split (World Bank)", 12, 28, 12, 9, TR_ANNUAL, unit="currencyUSD", fill=10,
               colors={"total": CAT[3], "gold": CAT[0], "ex_gold": CAT[7]}),
    timeseries("United States — annual reserves split (World Bank)", 0, 37, 12, 9, US_ANNUAL, unit="currencyUSD", fill=10,
               colors={"total": CAT[3], "gold": CAT[0], "ex_gold": CAT[7]}),
    timeseries("United States — monthly reserves ex gold (FRED)", 12, 37, 12, 9, US_MONTHLY, unit="currencyUSD", fill=10,
               colors={"US reserves ex gold (FRED)": CAT[0]},
               description="Shown once FRED_API_KEY is configured."),
    timeseries("Euro area — monthly reserve assets (ECB)", 0, 46, 12, 9, EA_MONTHLY, unit="currencyUSD", fill=10,
               colors={"ecb_usd": CAT[4], "ecb_eur": CAT[4]},
               description="Series currency is in the legend (ecb_usd or ecb_eur)."),
    timeseries("Euro area — annual reserves split (World Bank)", 12, 46, 12, 9, EA_ANNUAL, unit="currencyUSD", fill=10,
               colors={"total": CAT[3], "gold": CAT[0], "ex_gold": CAT[7]}),
    barchart("Gold share of total reserves, %", 0, 55, 12, 10, GOLD_SHARE, unit="percent", color=CAT[3]),
    table("Latest year, all countries", 12, 55, 12, 10,
          """SELECT DISTINCT ON (country_iso3) country AS "Country", period_date AS "Year", value_usd AS "Total USD"
             FROM reserves WHERE metric='total' AND source='worldbank' AND value_usd IS NOT NULL
             ORDER BY country_iso3, period_date DESC""",
          sort=("Total USD", True),
          overrides=[{"matcher": {"id": "byName", "options": "Total USD"}, "properties": [{"id": "unit", "value": "currencyUSD"}]},
                     {"matcher": {"id": "byName", "options": "Year"}, "properties": [{"id": "unit", "value": "dateTimeAsIsoNoDateIfToday"}]}]),
]

write(dashboard("reserves", "Reserve Assets", panels, ["economy"], refresh="1h", time_from="now-25y",
                description="Official reserve assets (FX + gold) per country: World Bank annual, ECB monthly, TCMB weekly, FRED monthly."),
      "reserves")

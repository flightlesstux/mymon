from _lib import CAT, dashboard, barchart, geomap, marker_layer, stat, target, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

LIVESTOCK = nl_multi(["cattle_count", "pig_count", "chicken_count"], "cbs")
LAND_USE = nl_multi(["arable_land", "horticulture_open", "horticulture_glass", "grassland"], "cbs")

FARMS_REGIONAL_LATEST = """
SELECT DISTINCT ON (m.region_code) r.name AS "Province", r.lat, r.lon,
       m.value AS "Farms", m.period_date AS "Year"
FROM region_metric m JOIN region r ON r.code = m.region_code
WHERE m.indicator='farm_count' AND m.source='cbs'
ORDER BY m.region_code, m.period_date DESC
"""

FARMS_REGIONAL_BAR = """
SELECT r.name AS "Province", m.value AS "Farms"
FROM region_metric m JOIN region r ON r.code = m.region_code
WHERE m.indicator='farm_count' AND m.source='cbs'
  AND m.period_date = (SELECT max(period_date) FROM region_metric
                        WHERE indicator='farm_count' AND source='cbs')
ORDER BY m.value DESC
"""

CATTLE_REGIONAL_TREND = """
SELECT m.period_date AS time, r.name AS metric, m.value
FROM region_metric m JOIN region r ON r.code = m.region_code
WHERE m.indicator='cattle_count' AND m.source='cbs' AND $__timeFilter(m.period_date)
ORDER BY 1
"""

_PROVINCES = ["Groningen", "Fryslân", "Drenthe", "Overijssel", "Flevoland", "Gelderland",
              "Utrecht", "Noord-Holland", "Zuid-Holland", "Zeeland", "Noord-Brabant", "Limburg"]
PROVINCE_COLORS = {name: CAT[i % len(CAT)] for i, name in enumerate(_PROVINCES)}

panels = [
    stat("Farms, national", 0, 0, 5, 4, nl_latest("farm_count", "cbs"),
         unit="short", decimals=0, color=CAT[0],
         description="Down from 97,390 in 2000 — steady farm consolidation."),
    stat("Cattle", 5, 0, 5, 4, nl_latest("cattle_count", "cbs"), unit="short", decimals=0,
         color=CAT[1]),
    stat("Pigs", 10, 0, 5, 4, nl_latest("pig_count", "cbs"), unit="short", decimals=0,
         color=CAT[3]),
    stat("Chickens", 15, 0, 5, 4, nl_latest("chicken_count", "cbs"), unit="short", decimals=0,
         color=CAT[6]),
    stat("Agricultural land", 20, 0, 4, 4, nl_latest("agricultural_land", "cbs"),
         unit="short", decimals=0, color=CAT[2], description="Hectares."),

    timeseries("Number of farms", 0, 4, 12, 9, nl("farm_count", "cbs"), unit="short",
               decimals=0, colors={"value": CAT[0]}, fill=15,
               description="CBS 81302ned, annual since 2000."),
    timeseries("Livestock", 12, 4, 12, 9, LIVESTOCK, unit="short", decimals=0,
               colors={"cattle_count": CAT[1], "pig_count": CAT[3], "chicken_count": CAT[6]},
               fill=0, legend="right"),

    timeseries("Land use by category", 0, 13, 24, 9, LAND_USE, unit="short", decimals=0,
               colors={"arable_land": CAT[0], "horticulture_open": CAT[2],
                       "horticulture_glass": CAT[3], "grassland": CAT[6]},
               fill=15, legend="right", description="Hectares."),

    geomap("Farms by province, latest year", 0, 22, 14, 13,
           [marker_layer("Provinces", "A", size_field="Farms", color_field="Farms",
                         size=(10, 32), color_scheme="continuous-GnYlRd", opacity=0.85,
                         text_field="Province")],
           targets=[target(FARMS_REGIONAL_LATEST, "A", "table")],
           view={"id": "coords", "lat": 52.1, "lon": 5.4, "zoom": 6.8, "allLayers": True},
           description="CBS 80780ned, farm count by province."),
    barchart("Farms by province, ranked", 14, 22, 10, 13, FARMS_REGIONAL_BAR,
             unit="short", color=CAT[0]),

    timeseries("Cattle by province", 0, 35, 24, 10, CATTLE_REGIONAL_TREND, unit="short",
               decimals=0, colors=PROVINCE_COLORS, fill=0, legend="right",
               description="All 12 provinces, annual."),
]

write(dashboard("nl-agriculture", "NL: Agriculture", panels, ["netherlands"], refresh="1h",
                time_from="2000-01-01T00:00:00Z",
                description="Dutch farm count, livestock and land use, national and by "
                            "province, annual since 2000."),
      "NL/nl-agriculture")

from _lib import CAT, dashboard, barchart, geomap, marker_layer, stat, table, target, timeseries, write

LATEST = """
SELECT DISTINCT ON (network_id) city AS "City", lat, lon, free_bikes AS "Free bikes",
       empty_slots AS "Empty docks", stations AS "Stations", ts AS "Updated"
FROM bike_network
ORDER BY network_id, ts DESC
"""

RANKED_BAR = """
SELECT city AS "City", free_bikes AS "Free bikes"
FROM bike_network
WHERE ts = (SELECT max(ts) FROM bike_network)
ORDER BY free_bikes DESC
"""

TREND = """
SELECT ts AS time, city AS metric, free_bikes AS value FROM bike_network
WHERE $__timeFilter(ts) ORDER BY 1
"""

_CITIES = ["Paris", "New York", "London", "Barcelona", "Chicago", "Washington, DC", "Berlin",
           "Oslo", "Buenos Aires", "San Francisco Bay Area", "Madrid", "Toronto", "Boston",
           "Lyon", "Hamburg"]
CITY_COLORS = {name: CAT[i % len(CAT)] for i, name in enumerate(_CITIES)}

panels = [
    stat("Networks tracked", 0, 0, 4, 4,
         "SELECT count(DISTINCT network_id) AS value FROM bike_network "
         "WHERE ts = (SELECT max(ts) FROM bike_network)",
         unit="short", decimals=0, color=CAT[0]),
    stat("Total free bikes right now", 4, 0, 6, 4,
         "SELECT sum(free_bikes) AS value FROM bike_network "
         "WHERE ts = (SELECT max(ts) FROM bike_network)",
         unit="short", decimals=0, color=CAT[2]),
    stat("Total empty docks right now", 10, 0, 6, 4,
         "SELECT sum(empty_slots) AS value FROM bike_network "
         "WHERE ts = (SELECT max(ts) FROM bike_network)",
         unit="short", decimals=0, color=CAT[3]),
    stat("Total stations tracked", 16, 0, 8, 4,
         "SELECT sum(stations) AS value FROM bike_network "
         "WHERE ts = (SELECT max(ts) FROM bike_network)",
         unit="short", decimals=0, color=CAT[1]),

    geomap("Free bikes right now, by city", 0, 4, 14, 13,
           [marker_layer("Cities", "A", size_field="Free bikes", color_field="Free bikes",
                         size=(8, 32), color_scheme="continuous-GnYlRd", opacity=0.85,
                         text_field="City")],
           targets=[target(LATEST, "A", "table")],
           view={"id": "zero", "lat": 25, "lon": -10, "zoom": 2.2, "allLayers": True},
           description="CityBikes, 15 major-city networks — a curated set, not exhaustive "
                       "(800+ networks exist worldwide)."),
    barchart("Free bikes right now, ranked", 14, 4, 10, 13, RANKED_BAR, unit="short", color=CAT[2]),

    table("Current status, all cities", 0, 17, 24, 9, LATEST,
          overrides=[{"matcher": {"id": "byName", "options": "Updated"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIso"}]}]),

    timeseries("Free bikes over time, by city", 0, 26, 24, 10, TREND, unit="short", decimals=0,
               colors=CITY_COLORS, fill=0, legend="right",
               description="Polled every 15 minutes — daily commute rhythms show up "
                           "within a few days of history."),
]

write(dashboard("global-bike-share", "Global: Bike Share", panels, ["global"], refresh="15m",
                time_from="now-7d",
                description="Live bike-share station counts for 15 major cities "
                            "worldwide (CityBikes): free bikes, empty docks, stations."),
      "global-bike-share")

from _lib import CAT, dashboard, barchart, geomap, marker_layer, stat, table, target, timeseries, write

# Netherlands bounding box (with a small margin) — aircraft_state already collects all of
# Europe for the World Overview map (OpenSky); this just filters to what's currently over NL.
NL_BOX = "lat BETWEEN 50.6 AND 53.7 AND lon BETWEEN 3.2 AND 7.3"

AIRCRAFT_NOW = f"""
SELECT icao24, callsign, country AS "Country", lat, lon, alt_m AS "Altitude m",
       velocity AS "Speed m/s", heading
FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX}
"""

AIRCRAFT_COUNT = f"""
SELECT count(*) AS aircraft FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX}
"""

DISTINCT_24H = f"""
SELECT count(DISTINCT icao24) AS aircraft FROM aircraft_state
WHERE ts > now() - interval '24 hours' AND {NL_BOX}
"""

AVG_ALT_NOW = f"""
SELECT round(avg(alt_m)::numeric, 0) AS value FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX} AND alt_m IS NOT NULL
"""

AVG_SPEED_NOW = f"""
SELECT round(avg(velocity)::numeric, 0) AS value FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX} AND velocity IS NOT NULL
"""

AIRCRAFT_TABLE = f"""
SELECT callsign AS "Callsign", country AS "Country", round(alt_m::numeric, 0) AS "Altitude m",
       round(velocity::numeric, 0) AS "Speed m/s", round(heading::numeric, 0) AS "Heading"
FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX} AND callsign IS NOT NULL
ORDER BY alt_m DESC NULLS LAST LIMIT 50
"""

COUNTRY_BREAKDOWN = f"""
SELECT country AS "Country of registration", count(*) AS "Aircraft"
FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX} AND country IS NOT NULL
GROUP BY country ORDER BY count(*) DESC LIMIT 12
"""

COUNT_TREND = f"""
SELECT ts AS time, count(*) AS value FROM aircraft_state
WHERE $__timeFilter(ts) AND {NL_BOX}
GROUP BY ts ORDER BY ts
"""

AVG_ALT_TREND = f"""
SELECT ts AS time, avg(alt_m) AS value FROM aircraft_state
WHERE $__timeFilter(ts) AND {NL_BOX} AND alt_m IS NOT NULL
GROUP BY ts ORDER BY ts
"""

AVG_SPEED_TREND = f"""
SELECT ts AS time, avg(velocity) AS value FROM aircraft_state
WHERE $__timeFilter(ts) AND {NL_BOX} AND velocity IS NOT NULL
GROUP BY ts ORDER BY ts
"""

layers = [
    marker_layer("Aircraft", "aircraft", color_field="Altitude m", size=(6, 6),
                 color_scheme="continuous-BlYlRd", min_=0, max_=12000, opacity=0.9,
                 text_field="callsign"),
]

panels = [
    stat("Aircraft over NL right now", 0, 0, 6, 4, AIRCRAFT_COUNT, decimals=0, color=CAT[2]),
    stat("Distinct aircraft, last 24h", 6, 0, 6, 4, DISTINCT_24H, decimals=0, color=CAT[0]),
    stat("Average altitude now", 12, 0, 6, 4, AVG_ALT_NOW, unit="lengthm", decimals=0,
         color=CAT[1]),
    stat("Average speed now", 18, 0, 6, 4, AVG_SPEED_NOW, unit="velocityms", decimals=0,
         color=CAT[3]),

    geomap("Aircraft currently over the Netherlands, by altitude", 0, 4, 24, 13, layers,
           view={"id": "coords", "lat": 52.1, "lon": 5.1, "zoom": 7.3, "allLayers": True},
           targets=[target(AIRCRAFT_NOW, "aircraft", "table")],
           description="OpenSky Network, latest snapshot (live only, no historical query). "
                       "Colour = altitude, dark blue near ground to yellow/red cruising."),

    timeseries("Aircraft count over NL", 0, 17, 12, 8, COUNT_TREND, decimals=0,
               colors={"value": CAT[2]}, fill=20, points=True,
               description="Day/night flight pattern — expect it to drop overnight. Depth "
                           "grows from whenever OpenSky was enabled; not backfillable."),
    barchart("Aircraft by country of registration, right now", 12, 17, 12, 8, COUNTRY_BREAKDOWN,
             unit="short", color=CAT[0]),

    timeseries("Average altitude over NL", 0, 25, 12, 8, AVG_ALT_TREND, unit="lengthm",
               decimals=0, colors={"value": CAT[1]}, fill=15),
    timeseries("Average speed over NL", 12, 25, 12, 8, AVG_SPEED_TREND, unit="velocityms",
               decimals=0, colors={"value": CAT[3]}, fill=15),

    table("Aircraft over NL now, by altitude", 0, 33, 24, 12, AIRCRAFT_TABLE,
          sort=("Altitude m", True),
          overrides=[{"matcher": {"id": "byName", "options": "Altitude m"},
                      "properties": [{"id": "unit", "value": "lengthm"}]},
                     {"matcher": {"id": "byName", "options": "Speed m/s"},
                      "properties": [{"id": "unit", "value": "velocityms"}]}]),
]

write(dashboard("nl-aircraft", "NL: Aircraft", panels, ["netherlands"], refresh="1m",
                time_from="now-24h",
                description="Aircraft currently over the Netherlands (OpenSky), live only, "
                            "no historical backfill possible for this one."),
      "NL/nl-aircraft")

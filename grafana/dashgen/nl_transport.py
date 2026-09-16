from _lib import CAT, dashboard, geomap, marker_layer, stat, table, target, timeseries, write

# Netherlands bounding box (with a small margin) — aircraft_state already collects all of
# Europe for the World Overview map; this just filters to what's currently over NL.
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

AIRCRAFT_TABLE = f"""
SELECT callsign AS "Callsign", country AS "Country", round(alt_m::numeric, 0) AS "Altitude m",
       round(velocity::numeric, 0) AS "Speed m/s", round(heading::numeric, 0) AS "Heading"
FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {NL_BOX} AND callsign IS NOT NULL
ORDER BY alt_m DESC NULLS LAST LIMIT 50
"""

AIRCRAFT_COUNT_TREND = f"""
SELECT ts AS time, count(*) AS value FROM aircraft_state
WHERE ts > now() - interval '24 hours' AND {NL_BOX}
GROUP BY ts ORDER BY ts
"""

layers = [
    marker_layer("Aircraft", "aircraft", size=(5, 5), fixed_color=CAT[2], opacity=0.85,
                 text_field="callsign"),
]

panels = [
    stat("Aircraft over NL right now", 0, 0, 8, 4, AIRCRAFT_COUNT, decimals=0, color=CAT[2]),
    stat("NS active train disruptions", 8, 0, 8, 4,
         "SELECT period_date AS time, value FROM price_index WHERE country_iso3='NLD' "
         "AND indicator='ns_disruptions_active' AND source='ns' "
         "ORDER BY period_date DESC LIMIT 1",
         decimals=0, color=CAT[1],
         description="Live-only (no historical API); shows 'No data' until NS_API_KEY is "
                     "set — free instant signup at apiportal.ns.nl."),
    stat("...of which unplanned (STORING)", 16, 0, 8, 4,
         "SELECT period_date AS time, value FROM price_index WHERE country_iso3='NLD' "
         "AND indicator='ns_disruptions_unplanned' AND source='ns' "
         "ORDER BY period_date DESC LIMIT 1",
         decimals=0, color=CAT[7]),

    geomap("Aircraft currently over the Netherlands", 0, 4, 24, 13, layers,
           view={"id": "coords", "lat": 52.1, "lon": 5.1, "zoom": 7.3, "allLayers": True},
           targets=[target(AIRCRAFT_NOW, "aircraft", "table")],
           description="OpenSky Network, latest snapshot (live only, no historical query)."),

    timeseries("Aircraft count over NL, last 24 h", 0, 17, 24, 8, AIRCRAFT_COUNT_TREND,
               decimals=0, colors={"value": CAT[2]}, fill=20, points=True,
               description="Day/night flight pattern — expect it to drop overnight."),

    table("Aircraft over NL now, by altitude", 0, 25, 24, 12, AIRCRAFT_TABLE,
          sort=("Altitude m", True),
          overrides=[{"matcher": {"id": "byName", "options": "Altitude m"},
                      "properties": [{"id": "unit", "value": "lengthm"}]},
                     {"matcher": {"id": "byName", "options": "Speed m/s"},
                      "properties": [{"id": "unit", "value": "velocityms"}]}]),
]

write(dashboard("nl-transport", "NL: Transport", panels, ["netherlands"], refresh="1m",
                time_from="now-24h",
                description="Aircraft currently over the Netherlands (OpenSky) and NS train "
                            "disruptions — both live-only, no historical backfill possible."),
      "NL/nl-transport")

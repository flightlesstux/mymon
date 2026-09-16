from _lib import CAT, dashboard, barchart, geomap, marker_layer, stat, table, target, timeseries, write

NEXT_LAUNCH = """
SELECT name AS "Mission", provider AS "Provider", rocket AS "Rocket",
       pad_name AS "Pad", country AS "Country", net AS "Launch time", status AS "Status"
FROM space_launch WHERE net > now() ORDER BY net ASC LIMIT 15
"""
RECENT_LAUNCHES = """
SELECT name AS "Mission", provider AS "Provider", rocket AS "Rocket",
       country AS "Country", net AS "Launch time", status AS "Status"
FROM space_launch WHERE net <= now() ORDER BY net DESC LIMIT 15
"""
LAUNCH_MAP = """
SELECT name AS "Mission", pad_name AS "Pad", country AS "Country", lat, lon, net AS "Time"
FROM space_launch WHERE lat IS NOT NULL AND lon IS NOT NULL
ORDER BY net DESC LIMIT 40
"""
LAUNCHES_BY_COUNTRY = """
SELECT country AS "Country", count(*) AS "Launches"
FROM space_launch WHERE country IS NOT NULL GROUP BY country ORDER BY 2 DESC LIMIT 15
"""

ASTRONAUT_ROSTER = """
SELECT name AS "Name", craft AS "Spacecraft" FROM astronaut ORDER BY craft, name
"""

EVENTS_MAP = """
SELECT title AS "Event", category AS "Category", lat, lon, event_date AS "Observed",
       magnitude_value AS "Magnitude", magnitude_unit AS "Unit"
FROM natural_event ORDER BY event_date DESC LIMIT 500
"""
EVENTS_TABLE = """
SELECT title AS "Event", category AS "Category", event_date AS "Observed",
       magnitude_value AS "Magnitude", magnitude_unit AS "Unit"
FROM natural_event ORDER BY event_date DESC LIMIT 100
"""
EVENTS_BY_CATEGORY = """
SELECT category AS "Category", count(*) AS "Open events"
FROM natural_event GROUP BY category ORDER BY 2 DESC
"""

XRAY_FLUX = """
SELECT ts AS time, xray_flux AS "X-ray flux W/m²" FROM space_weather
WHERE xray_flux IS NOT NULL AND $__timeFilter(ts) ORDER BY 1
"""
SATELLITE_COUNT = """
SELECT ts AS time, satellites_active AS "Active satellites" FROM space_weather
WHERE satellites_active IS NOT NULL AND $__timeFilter(ts) ORDER BY 1
"""

panels = [
    stat("People currently in space", 0, 0, 5, 4,
         "SELECT count(*) AS value FROM astronaut", unit="short", decimals=0, color=CAT[0]),
    stat("Actively tracked orbital objects", 5, 0, 5, 4,
         "SELECT satellites_active AS value FROM space_weather "
         "WHERE satellites_active IS NOT NULL ORDER BY ts DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[6], description="Celestrak, updates every 2h."),
    stat("Current solar flare class", 10, 0, 5, 4,
         "SELECT xray_flare_class AS value FROM space_weather "
         "WHERE xray_flare_class IS NOT NULL ORDER BY ts DESC LIMIT 1",
         color=CAT[3], text_value=True,
         description="GOES X-ray long-channel (0.1-0.8nm). A/B = quiet, C = common, "
                     "M = moderate, X = major."),
    stat("Open natural hazard events tracked", 15, 0, 5, 4,
         "SELECT count(*) AS value FROM natural_event", unit="short", decimals=0, color=CAT[2],
         description="Volcanoes, storms, sea/lake ice, floods, drought, landslides, "
                     "temp. extremes, dust/haze — wildfires excluded (thousands of "
                     "small local fires would swamp everything else)."),
    stat("Next launch", 20, 0, 4, 4,
         "SELECT net AS value FROM space_launch WHERE net > now() ORDER BY net ASC LIMIT 1",
         unit="dateTimeAsIso", color=CAT[1], text_value=True, description="UTC."),

    table("Astronaut roster", 0, 4, 8, 11, ASTRONAUT_ROSTER,
          description="Open Notify — who's aboard the ISS and Tiangong right now."),
    geomap("Upcoming & recent launch sites", 8, 4, 16, 11,
           [marker_layer("Launches", "A", text_field="Mission", fixed_color=CAT[1],
                         size=(8, 8))],
           targets=[target(LAUNCH_MAP, "A", "table")],
           view={"id": "zero", "lat": 20, "lon": 20, "zoom": 1.6, "allLayers": True}),

    table("Upcoming launches", 0, 15, 12, 12, NEXT_LAUNCH,
          overrides=[{"matcher": {"id": "byName", "options": "Launch time"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIso"}]}]),
    table("Recent launches", 12, 15, 12, 12, RECENT_LAUNCHES,
          overrides=[{"matcher": {"id": "byName", "options": "Launch time"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIso"}]}]),

    barchart("Launches tracked, by country", 0, 27, 24, 10, LAUNCHES_BY_COUNTRY,
             unit="short", color=CAT[1],
             description="Rolling window of the last ~20 upcoming + 20 flown launches "
                         "this source keeps — not a full historical count."),

    geomap("Open natural hazard events", 0, 37, 14, 13,
           [marker_layer("Events", "A", size_field="Magnitude", text_field="Event",
                         fixed_color=CAT[3], size=(6, 22))],
           targets=[target(EVENTS_MAP, "A", "table")],
           view={"id": "zero", "lat": 20, "lon": 0, "zoom": 1.4, "allLayers": True},
           description="NASA EONET, excludes wildfires. Hover a marker for category, "
                       "magnitude and when it was last observed."),
    barchart("Open events by category", 14, 37, 10, 13, EVENTS_BY_CATEGORY,
             unit="short", color=CAT[3]),

    table("Recent natural hazard events", 0, 50, 24, 12, EVENTS_TABLE,
          overrides=[{"matcher": {"id": "byName", "options": "Observed"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIso"}]}]),

    timeseries("Solar X-ray flux (GOES long channel)", 0, 62, 12, 9, XRAY_FLUX,
               decimals=9, colors={"X-ray flux W/m²": CAT[6]}, fill=15,
               description="B-class and above is worth watching; C/M/X can affect HF "
                           "radio and, at the top end, satellite electronics."),
    timeseries("Actively tracked orbital objects", 12, 62, 12, 9, SATELLITE_COUNT,
               unit="short", decimals=0, colors={"Active satellites": CAT[0]}, fill=15,
               points=True, description="Celestrak, updates at most once per 2 hours."),
]

write(dashboard("global-space-monitor", "Global: Space Monitor", panels, ["global"],
                refresh="30m", time_from="now-30d",
                description="What's happening in near-Earth space and on Earth's "
                            "surface right now: who's in orbit, upcoming and recent "
                            "launches, solar activity, tracked satellites, and open "
                            "natural hazard events worldwide."),
      "global-space-monitor")

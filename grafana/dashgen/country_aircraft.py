"""One dashboard generator, six countries — aircraft_state already collects the whole
"Europe, the Middle East and Türkiye" OpenSky bounding box for World Overview; this just
filters to each country the same way NL: Aircraft does. Zero new collector code.
"""

import _lib
from _lib import CAT, barchart, dashboard, geomap, marker_layer, stat, table, target, timeseries, write

COUNTRIES = [
    ("DE", "Germany", 47.3, 55.1, 5.9, 15.0, 51.1, 10.4, 5.8),
    ("IT", "Italy", 36.6, 47.1, 6.6, 18.5, 42.5, 12.5, 5.3),
    ("ES", "Spain", 36.0, 43.8, -9.3, 3.3, 40.2, -3.7, 5.3),
    ("GR", "Greece", 34.8, 41.7, 19.4, 28.2, 39.0, 22.9, 6.2),
    ("TR", "Turkey", 36.0, 42.1, 26.0, 44.8, 39.0, 35.0, 5.3),
    ("FR", "France", 41.3, 51.1, -5.1, 9.6, 46.6, 2.2, 5.4),
]
# (code, name, lat_min, lat_max, lon_min, lon_max, center_lat, center_lon, zoom)

for code, name, lat_min, lat_max, lon_min, lon_max, clat, clon, zoom in COUNTRIES:
    _lib._id = 0

    box = f"lat BETWEEN {lat_min} AND {lat_max} AND lon BETWEEN {lon_min} AND {lon_max}"

    aircraft_now = f"""
    SELECT icao24, callsign, country AS "Country", lat, lon, alt_m AS "Altitude m",
           velocity AS "Speed m/s", heading
    FROM aircraft_state
    WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {box}
    """
    count_now = f"""
    SELECT count(*) AS aircraft FROM aircraft_state
    WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {box}
    """
    distinct_24h = f"""
    SELECT count(DISTINCT icao24) AS aircraft FROM aircraft_state
    WHERE ts > now() - interval '24 hours' AND {box}
    """
    avg_alt_now = f"""
    SELECT round(avg(alt_m)::numeric, 0) AS value FROM aircraft_state
    WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {box} AND alt_m IS NOT NULL
    """
    avg_speed_now = f"""
    SELECT round(avg(velocity)::numeric, 0) AS value FROM aircraft_state
    WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {box} AND velocity IS NOT NULL
    """
    aircraft_table = f"""
    SELECT callsign AS "Callsign", country AS "Country", round(alt_m::numeric, 0) AS "Altitude m",
           round(velocity::numeric, 0) AS "Speed m/s", round(heading::numeric, 0) AS "Heading"
    FROM aircraft_state
    WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {box} AND callsign IS NOT NULL
    ORDER BY alt_m DESC NULLS LAST LIMIT 50
    """
    country_breakdown = f"""
    SELECT country AS "Country of registration", count(*) AS "Aircraft"
    FROM aircraft_state
    WHERE ts = (SELECT max(ts) FROM aircraft_state) AND {box} AND country IS NOT NULL
    GROUP BY country ORDER BY count(*) DESC LIMIT 12
    """
    count_trend = f"""
    SELECT ts AS time, count(*) AS value FROM aircraft_state
    WHERE $__timeFilter(ts) AND {box}
    GROUP BY ts ORDER BY ts
    """
    avg_alt_trend = f"""
    SELECT ts AS time, avg(alt_m) AS value FROM aircraft_state
    WHERE $__timeFilter(ts) AND {box} AND alt_m IS NOT NULL
    GROUP BY ts ORDER BY ts
    """
    avg_speed_trend = f"""
    SELECT ts AS time, avg(velocity) AS value FROM aircraft_state
    WHERE $__timeFilter(ts) AND {box} AND velocity IS NOT NULL
    GROUP BY ts ORDER BY ts
    """

    layers = [
        marker_layer("Aircraft", "aircraft", color_field="Altitude m", size=(6, 6),
                     color_scheme="continuous-BlYlRd", min_=0, max_=12000, opacity=0.9,
                     text_field="callsign"),
    ]

    panels = [
        stat(f"Aircraft over {name} right now", 0, 0, 6, 4, count_now, decimals=0, color=CAT[2]),
        stat("Distinct aircraft, last 24h", 6, 0, 6, 4, distinct_24h, decimals=0, color=CAT[0]),
        stat("Average altitude now", 12, 0, 6, 4, avg_alt_now, unit="lengthm", decimals=0,
             color=CAT[1]),
        stat("Average speed now", 18, 0, 6, 4, avg_speed_now, unit="velocityms", decimals=0,
             color=CAT[3]),

        geomap(f"Aircraft currently over {name}, by altitude", 0, 4, 24, 13, layers,
               view={"id": "coords", "lat": clat, "lon": clon, "zoom": zoom, "allLayers": True},
               targets=[target(aircraft_now, "aircraft", "table")],
               description="OpenSky Network, latest snapshot (live only, no historical "
                           "query). Colour = altitude, dark blue near ground to "
                           "yellow/red cruising."),

        timeseries(f"Aircraft count over {name}", 0, 17, 12, 8, count_trend, decimals=0,
                   colors={"value": CAT[2]}, fill=20, points=True,
                   description="Day/night flight pattern — depth grows from whenever "
                               "OpenSky was enabled; not backfillable."),
        barchart("Aircraft by country of registration, right now", 12, 17, 12, 8,
                 country_breakdown, unit="short", color=CAT[0]),

        timeseries(f"Average altitude over {name}", 0, 25, 12, 8, avg_alt_trend, unit="lengthm",
                   decimals=0, colors={"value": CAT[1]}, fill=15),
        timeseries(f"Average speed over {name}", 12, 25, 12, 8, avg_speed_trend,
                   unit="velocityms", decimals=0, colors={"value": CAT[3]}, fill=15),

        table(f"Aircraft over {name} now, by altitude", 0, 33, 24, 12, aircraft_table,
              sort=("Altitude m", True),
              overrides=[{"matcher": {"id": "byName", "options": "Altitude m"},
                          "properties": [{"id": "unit", "value": "lengthm"}]},
                         {"matcher": {"id": "byName", "options": "Speed m/s"},
                          "properties": [{"id": "unit", "value": "velocityms"}]}]),
    ]

    write(dashboard(f"{code.lower()}-aircraft", f"{name}: Aircraft", panels, [name.lower()],
                    refresh="1m", time_from="now-24h",
                    description=f"Aircraft currently over {name} (OpenSky), live only, "
                                f"no historical backfill possible for this one."),
          f"{code}/{code.lower()}-aircraft")

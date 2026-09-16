from _lib import CAT, dashboard, gauge, geomap, marker_layer, stat, table, target, timeseries, barchart, write

QUAKES_MAP = """
SELECT ts AS "Time", lat, lon, mag AS "Magnitude", depth_km AS "Depth km", place AS "Place"
FROM earthquake WHERE $__timeFilter(ts) AND mag >= 2.5 ORDER BY ts DESC LIMIT 5000
"""
TR_QUAKES_MAP = """
SELECT ts AS "Time", lat, lon, mag AS "Magnitude", depth_km AS "Depth km", place AS "Place"
FROM earthquake WHERE $__timeFilter(ts) AND lat BETWEEN 35 AND 43 AND lon BETWEEN 25 AND 45 ORDER BY ts DESC LIMIT 5000
"""
QUAKES_PER_DAY = """
SELECT $__timeGroupAlias(ts, '1d'),
  count(*) FILTER (WHERE mag >= 6) AS "M6+",
  count(*) FILTER (WHERE mag >= 5 AND mag < 6) AS "M5-6",
  count(*) FILTER (WHERE mag >= 4.5 AND mag < 5) AS "M4.5-5"
FROM earthquake WHERE $__timeFilter(ts) AND source='usgs' GROUP BY 1 ORDER BY 1
"""
BIGGEST = """
SELECT ts AS "Time", mag AS "Mag", depth_km AS "Depth km", place AS "Place", source AS "Source"
FROM earthquake WHERE $__timeFilter(ts) ORDER BY mag DESC NULLS LAST LIMIT 30
"""
MAG_SCATTER = """
SELECT ts AS time, mag AS "Magnitude" FROM earthquake WHERE $__timeFilter(ts) AND mag >= 4 ORDER BY ts
"""
KP = "SELECT ts AS time, kp AS \"Kp\" FROM space_weather WHERE $__timeFilter(ts) ORDER BY 1"
WIND = "SELECT ts AS time, solar_wind_speed AS \"Speed km/s\" FROM space_weather WHERE $__timeFilter(ts) AND solar_wind_speed IS NOT NULL ORDER BY 1"
BZ = "SELECT ts AS time, bz AS \"Bz nT\", solar_wind_density AS \"Density p/cm³\" FROM space_weather WHERE $__timeFilter(ts) AND bz IS NOT NULL ORDER BY 1"
CO2 = "SELECT month AS time, ppm AS \"Monthly mean\", trend_ppm AS \"Trend\" FROM co2_monthly WHERE $__timeFilter(month) ORDER BY 1"
CO2_YOY = """
SELECT a.month AS time, a.trend_ppm - b.trend_ppm AS "Year-over-year increase ppm"
FROM co2_monthly a JOIN co2_monthly b ON b.month = a.month - interval '1 year'
WHERE $__timeFilter(a.month) ORDER BY 1
"""
ISS_TRAIL = "SELECT ts AS \"Time\", lat, lon, altitude_km AS \"Altitude km\" FROM iss_position WHERE ts > now() - interval '3 hours' ORDER BY ts"
ISS_NOW = "SELECT ts AS \"Time\", lat, lon, 'ISS' AS name FROM iss_position ORDER BY ts DESC LIMIT 1"
ISS_ALT = "SELECT ts AS time, altitude_km AS \"Altitude km\" FROM iss_position WHERE $__timeFilter(ts) ORDER BY 1"
ISS_VEL = "SELECT ts AS time, velocity_kmh AS \"Velocity km/h\" FROM iss_position WHERE $__timeFilter(ts) ORDER BY 1"
BTC_HEIGHT = "SELECT ts AS time, block_height FROM btc_network WHERE $__timeFilter(ts) AND block_height IS NOT NULL ORDER BY 1"
BTC_HASH = "SELECT ts AS time, hashrate_ehs AS \"Hashrate EH/s\" FROM btc_network WHERE $__timeFilter(ts) AND hashrate_ehs IS NOT NULL ORDER BY 1"
BTC_FEES = """
SELECT ts AS time, fee_fast AS "Fast", fee_half_hour AS "30 min", fee_hour AS "1 h", fee_economy AS "Economy"
FROM btc_network WHERE $__timeFilter(ts) AND fee_fast IS NOT NULL ORDER BY 1
"""
BTC_MEMPOOL = "SELECT ts AS time, mempool_tx_count AS \"Unconfirmed tx\" FROM btc_network WHERE $__timeFilter(ts) AND mempool_tx_count IS NOT NULL ORDER BY 1"

mag_overrides = [{"matcher": {"id": "byName", "options": "Time"}, "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
                 {"matcher": {"id": "byName", "options": "Mag"},
                  "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                                 {"id": "color", "value": {"mode": "continuous-YlRd"}},
                                 {"id": "min", "value": 2}, {"id": "max", "value": 8}, {"id": "decimals", "value": 1}]}]

panels = [
    stat("Kp now", 0, 0, 4, 4, KP, decimals=1,
         thresholds=[{"color": "#0ca30c", "value": None}, {"color": "#fab219", "value": 4}, {"color": "#ec835a", "value": 5}, {"color": "#d03b3b", "value": 7}]),
    stat("Solar wind", 4, 0, 4, 4, WIND, unit="km/s", decimals=0, color=CAT[3]),
    stat("CO₂ Mauna Loa", 8, 0, 4, 4, "SELECT month AS time, ppm FROM co2_monthly WHERE month > now() - interval '3 years' ORDER BY 1", unit="ppm", decimals=1, color=CAT[7]),
    stat("Quakes M4.5+, 7 d", 12, 0, 4, 4, "SELECT count(*) FROM earthquake WHERE ts > now() - interval '7 days' AND mag >= 4.5", color=CAT[1], sparkline=False),
    stat("Bitcoin block height", 16, 0, 4, 4, BTC_HEIGHT, decimals=0, color=CAT[3]),
    stat("Fast fee sat/vB", 20, 0, 4, 4, "SELECT ts AS time, fee_fast FROM btc_network WHERE ts > now() - interval '24 hours' AND fee_fast IS NOT NULL ORDER BY 1", decimals=0, color=CAT[3]),

    geomap("Earthquakes M2.5+ in range", 0, 4, 16, 14,
           [marker_layer("Quakes", "A", size_field="Magnitude", color_field="Magnitude", size=(2, 24), color_scheme="continuous-YlRd", min_=2.5, max_=7.5, opacity=0.6)],
           targets=[target(QUAKES_MAP, "A", "table")],
           view={"id": "zero", "lat": 20, "lon": 20, "zoom": 1.6, "allLayers": True}),
    geomap("Türkiye and surroundings (AFAD + USGS)", 16, 4, 8, 14,
           [marker_layer("Quakes", "A", size_field="Magnitude", color_field="Magnitude", size=(2, 20), color_scheme="continuous-YlRd", min_=1, max_=7, opacity=0.7)],
           targets=[target(TR_QUAKES_MAP, "A", "table")],
           view={"id": "coords", "lat": 39, "lon": 35, "zoom": 4.6, "allLayers": True}),
    timeseries("Quakes per day by magnitude band (USGS)", 0, 18, 12, 8, QUAKES_PER_DAY, decimals=0, stack=True, fill=70, lw=1,
               colors={"M6+": CAT[7], "M5-6": CAT[1], "M4.5-5": CAT[3]}),
    table("Biggest in range", 12, 18, 12, 8, BIGGEST, overrides=mag_overrides),
    timeseries("Magnitude of every M4+ event", 0, 26, 24, 7, MAG_SCATTER, decimals=1, colors={"Magnitude": CAT[1]}, fill=0, points=True, lw=0,
               description="Each dot is one earthquake."),

    timeseries("Planetary Kp index (3-hour)", 0, 33, 8, 8, KP, decimals=1, colors={"Kp": CAT[6]}, fill=40, min_=0, max_=9,
               description="Kp 5+ = geomagnetic storm, aurora possible at mid-latitudes."),
    timeseries("Solar wind speed", 8, 33, 8, 8, WIND, unit="km/s", decimals=0, colors={"Speed km/s": CAT[3]}),
    timeseries("Bz and proton density", 16, 33, 8, 8, BZ, decimals=1, colors={"Bz nT": CAT[0], "Density p/cm³": CAT[4]}, fill=0,
               description="Sustained negative Bz couples the solar wind into Earth's magnetosphere."),

    geomap("ISS ground track, last 3 hours", 0, 41, 12, 10,
           [marker_layer("Track", "trail", size=(3, 3), fixed_color=CAT[0], opacity=0.8),
            marker_layer("Now", "now", size=(12, 12), fixed_color="#ffffff", opacity=1, symbol="img/icons/marker/star.svg", text_field="name")],
           targets=[target(ISS_TRAIL, "trail", "table"), target(ISS_NOW, "now", "table")],
           view={"id": "zero", "lat": 10, "lon": 0, "zoom": 1.3, "allLayers": True}),
    timeseries("ISS altitude", 12, 41, 6, 10, ISS_ALT, unit="lengthkm", decimals=1, colors={"Altitude km": CAT[6]}, fill=0),
    timeseries("ISS velocity", 18, 41, 6, 10, ISS_VEL, unit="velocitykmh", decimals=0, colors={"Velocity km/h": CAT[2]}, fill=0),

    timeseries("Atmospheric CO₂ at Mauna Loa (NOAA)", 0, 51, 16, 9, CO2, unit="ppm", decimals=1, colors={"Monthly mean": CAT[7], "Trend": CAT[3]}, fill=0),
    timeseries("CO₂ year-over-year growth", 16, 51, 8, 9, CO2_YOY, unit="ppm", decimals=2, colors={"Year-over-year increase ppm": CAT[1]}, fill=20),

    timeseries("Bitcoin network hashrate", 0, 60, 8, 8, BTC_HASH, decimals=0, colors={"Hashrate EH/s": CAT[3]}, fill=20,
               description="EH/s (exahashes per second)."),
    timeseries("Recommended fees, sat/vB", 8, 60, 8, 8, BTC_FEES, decimals=0,
               colors={"Fast": CAT[7], "30 min": CAT[1], "1 h": CAT[3], "Economy": CAT[2]}, fill=0),
    timeseries("Mempool unconfirmed transactions", 16, 60, 8, 8, BTC_MEMPOOL, unit="short", decimals=0, colors={"Unconfirmed tx": CAT[0]}, fill=30),
]

write(dashboard("earth-space", "Earth & Space", panels, ["mymon", "earth"], refresh="5m", time_from="now-7d",
                description="Earthquakes, geomagnetic activity, the ISS, CO₂ and the Bitcoin network."),
      "earth-space")

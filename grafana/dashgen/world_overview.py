from _lib import CAT, DS, dashboard, geomap, marker_layer, stat, table, target, write

CITY_NOW = """
SELECT DISTINCT ON (w.city)
  w.city AS "City", c.lat, c.lon,
  w.temp_c AS "Temp °C", w.humidity AS "Humidity %", w.wind_kph AS "Wind km/h",
  w.aqi_eu AS "AQI", w.ts AS "Observed"
FROM weather_current w JOIN city c ON c.city = w.city
WHERE w.ts > now() - interval '3 hours'
ORDER BY w.city, w.ts DESC
"""

QUAKES = """
SELECT ts AS "Time", lat, lon, mag AS "Magnitude", depth_km AS "Depth km", place AS "Place", source
FROM earthquake
WHERE ts > now() - interval '24 hours' AND mag >= 2.5
ORDER BY ts DESC
"""

ISS = """
SELECT ts AS "Time", lat, lon, altitude_km AS "Altitude km", velocity_kmh AS "Velocity km/h", 'ISS' AS name
FROM iss_position ORDER BY ts DESC LIMIT 1
"""

ISS_TRAIL = """
SELECT ts, lat, lon FROM iss_position WHERE ts > now() - interval '92 minutes' ORDER BY ts
"""

AIRCRAFT = """
SELECT icao24, callsign, country AS "Country", lat, lon, alt_m AS "Altitude m", heading
FROM aircraft_state
WHERE ts = (SELECT max(ts) FROM aircraft_state) AND lat IS NOT NULL AND lon IS NOT NULL
"""

AIRCRAFT_COUNT = """
SELECT count(*) AS aircraft FROM aircraft_state WHERE ts = (SELECT max(ts) FROM aircraft_state)
"""

def last(table, col, where="", order="ts"):
    return f"SELECT {col} FROM {table} {where} ORDER BY {order} DESC LIMIT 1"

def series(table, col, where, order="ts", limit=300):
    return f"SELECT {order} AS time, {col} AS value FROM {table} WHERE {where} ORDER BY {order} DESC LIMIT {limit}"

FX = "SELECT ts AS time, rate FROM fx_rate WHERE base='USD' AND quote='TRY' AND source='frankfurter' AND ts > now() - interval '30 days' ORDER BY ts"
EURUSD = "SELECT ts AS time, 1/rate AS rate FROM fx_rate WHERE base='USD' AND quote='EUR' AND source='frankfurter' AND ts > now() - interval '30 days' ORDER BY ts"
BTC = "SELECT ts AS time, price FROM crypto_tick WHERE symbol='BTC' AND ts > now() - interval '24 hours' ORDER BY ts"
GOLD = "SELECT period_date AS time, price FROM commodity_price WHERE commodity='gold' AND source='stooq' AND period_date > now() - interval '30 days' ORDER BY period_date"
BRENT = "SELECT period_date AS time, price FROM commodity_price WHERE commodity='brent' AND source='stooq' AND period_date > now() - interval '30 days' ORDER BY period_date"
KP = "SELECT ts AS time, kp FROM space_weather WHERE ts > now() - interval '24 hours' ORDER BY ts"
QUAKE_COUNT = "SELECT count(*) AS quakes FROM earthquake WHERE ts > now() - interval '24 hours' AND mag >= 4.5"
HOTTEST = """SELECT city || ' ' || round(temp_c,1) || '°C' AS hottest FROM (SELECT DISTINCT ON (city) city, temp_c FROM weather_current WHERE ts > now() - interval '3 hours' ORDER BY city, ts DESC) t ORDER BY temp_c DESC LIMIT 1"""
COLDEST = """SELECT city || ' ' || round(temp_c,1) || '°C' AS coldest FROM (SELECT DISTINCT ON (city) city, temp_c FROM weather_current WHERE ts > now() - interval '3 hours' ORDER BY city, ts DESC) t ORDER BY temp_c ASC LIMIT 1"""

map_targets = [
    target(CITY_NOW, "cities", "table"),
    target(QUAKES, "quakes", "table"),
    target(ISS, "iss", "table"),
    target(AIRCRAFT, "aircraft", "table"),
]
layers = [
    # Drawn first (bottom): thousands of small, low-opacity dots so they never compete
    # visually with the cities/quakes/ISS layers drawn on top of them.
    marker_layer("Aircraft (live)", "aircraft", size=(2, 2), fixed_color=CAT[2], opacity=0.45,
                 text_field=None),
    marker_layer("Earthquakes 24h", "quakes", size_field="Magnitude", color_field="Magnitude",
                 size=(3, 22), color_scheme="continuous-YlRd", min_=2.5, max_=7.5, opacity=0.65),
    marker_layer("Cities (temperature)", "cities", color_field="Temp °C", size=(9, 9),
                 color_scheme="continuous-BlYlRd", min_=-10, max_=40, opacity=0.95, text_field="City"),
    marker_layer("ISS", "iss", size=(12, 12), fixed_color="#ffffff", opacity=1,
                 symbol="img/icons/marker/star.svg", text_field="name"),
]

panels = [
    stat("BTC / USD", 0, 0, 4, 4, BTC, unit="currencyUSD", decimals=0, color=CAT[3]),
    stat("USD / TRY", 4, 0, 4, 4, FX, unit="none", decimals=2, color=CAT[1]),
    stat("EUR / USD", 8, 0, 4, 4, EURUSD, unit="none", decimals=4, color=CAT[0]),
    stat("Gold USD/oz", 12, 0, 4, 4, GOLD, unit="currencyUSD", decimals=0, color=CAT[3]),
    stat("Brent USD/bbl", 16, 0, 4, 4, BRENT, unit="currencyUSD", decimals=2, color=CAT[2]),
    stat("Kp index", 20, 0, 4, 4, KP, decimals=1, sparkline=True,
         thresholds=[{"color": "#0ca30c", "value": None}, {"color": "#fab219", "value": 4},
                     {"color": "#ec835a", "value": 5}, {"color": "#d03b3b", "value": 7}]),
    geomap("World right now — city temperatures, earthquakes (24 h, M2.5+), ISS, live aircraft",
           0, 4, 24, 18, layers,
           view={"id": "zero", "lat": 25, "lon": 15, "zoom": 1.7, "allLayers": True},
           targets=map_targets,
           description="Cities coloured by current temperature. Earthquake bubbles sized and coloured by "
                       "magnitude. Star = International Space Station. Small dots = aircraft over Europe "
                       "(OpenSky), latest snapshot — toggle the layer off in the panel legend if it's too busy."),
    stat("Hottest city", 0, 22, 5, 4, HOTTEST, color=CAT[7], sparkline=False, text_mode="value",
         color_mode="none", text_value=True),
    stat("Coldest city", 5, 22, 5, 4, COLDEST, color=CAT[0], sparkline=False, text_mode="value",
         color_mode="none", text_value=True),
    stat("M4.5+ quakes, 24 h", 10, 22, 5, 4, QUAKE_COUNT, color=CAT[1], sparkline=False),
    stat("ISS altitude", 15, 22, 5, 4, "SELECT ts AS time, altitude_km FROM iss_position WHERE ts > now() - interval '3 hours' ORDER BY ts",
         unit="lengthkm", decimals=0, color=CAT[6]),
    stat("Aircraft tracked", 20, 22, 4, 4, AIRCRAFT_COUNT, color=CAT[2], sparkline=False),
    table("Cities now", 0, 26, 12, 12,
          """SELECT DISTINCT ON (city) city AS "City", temp_c AS "°C", feels_like_c AS "Feels", humidity AS "Hum %",
                    wind_kph AS "Wind", aqi_eu AS "AQI", precip_mm AS "Rain mm"
             FROM weather_current WHERE ts > now() - interval '3 hours' ORDER BY city, ts DESC""",
          sort=("°C", True),
          overrides=[{"matcher": {"id": "byName", "options": "°C"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
                                     {"id": "color", "value": {"mode": "continuous-BlYlRd"}},
                                     {"id": "min", "value": -10}, {"id": "max", "value": 40}]},
                     {"matcher": {"id": "byName", "options": "AQI"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
                                     {"id": "color", "value": {"mode": "continuous-GrYlRd"}},
                                     {"id": "min", "value": 0}, {"id": "max", "value": 100}]}]),
    table("Strongest earthquakes, 24 h", 12, 26, 12, 12,
          """SELECT ts AS "Time", mag AS "Mag", depth_km AS "Depth km", place AS "Place"
             FROM earthquake WHERE ts > now() - interval '24 hours' ORDER BY mag DESC NULLS LAST LIMIT 25""",
          overrides=[{"matcher": {"id": "byName", "options": "Time"}, "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
                     {"matcher": {"id": "byName", "options": "Mag"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                                     {"id": "color", "value": {"mode": "continuous-YlRd"}},
                                     {"id": "min", "value": 2}, {"id": "max", "value": 8}, {"id": "decimals", "value": 1}]}]),
]

write(dashboard("world-overview", "World Overview", panels, ["home"], refresh="1m", time_from="now-24h",
                description="One screen: markets, weather in 21 cities, earthquakes and the ISS."),
      "world-overview")

from _lib import dashboard, geomap, marker_layer, table, target, timeseries, write
from _nl_common import CITY_COLORS, CITY_LIST_SQL, NL_CITIES, RANGE_START

CITY_NOW = f"""
SELECT DISTINCT ON (w.city)
  w.city AS "City", c.lat, c.lon, w.temp_c AS "Temp °C", w.feels_like_c AS "Feels °C",
  w.humidity AS "Humidity %", w.wind_kph AS "Wind km/h", w.pressure_hpa AS "Pressure hPa",
  w.aqi_eu AS "AQI", w.pm2_5 AS "PM2.5", w.pm10 AS "PM10", w.ts AS "Observed"
FROM weather_current w JOIN city c ON c.city = w.city
WHERE w.city IN ({CITY_LIST_SQL}) AND w.ts > now() - interval '3 hours'
ORDER BY w.city, w.ts DESC
"""

CITY_TEMP_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, avg(temp_c) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_START}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

CITY_HUMIDITY_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, avg(humidity) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_START}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

CITY_WIND_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, avg(wind_kph) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_START}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

CITY_AQI_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, avg(aqi_eu) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_START}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

CITY_RAIN_TREND = f"""
SELECT $__timeGroupAlias(ts, '1d'), city AS metric, sum(precip_mm) AS value
FROM weather_current
WHERE city IN ({CITY_LIST_SQL}) AND ts >= '{RANGE_START}' AND $__timeFilter(ts)
GROUP BY 1, 2 ORDER BY 1
"""

layers = [
    marker_layer("Cities (temperature)", "cities", color_field="Temp °C", size=(16, 16),
                 color_scheme="continuous-BlYlRd", min_=-5, max_=30, opacity=0.95, text_field="City"),
]

panels = [
    geomap("Netherlands — current temperature", 0, 0, 24, 13, layers,
           view={"id": "coords", "lat": 52.1, "lon": 5.1, "zoom": 7.3, "allLayers": True},
           targets=[target(CITY_NOW, "cities", "table")],
           description=f"{', '.join(NL_CITIES)} — latest reading."),

    table("Current conditions", 0, 13, 24, 9, CITY_NOW,
          overrides=[{"matcher": {"id": "byName", "options": "Temp °C"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
                                     {"id": "color", "value": {"mode": "continuous-BlYlRd"}},
                                     {"id": "min", "value": -5}, {"id": "max", "value": 30}]},
                     {"matcher": {"id": "byName", "options": "AQI"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
                                     {"id": "color", "value": {"mode": "continuous-GrYlRd"}},
                                     {"id": "min", "value": 0}, {"id": "max", "value": 100}]},
                     {"matcher": {"id": "byName", "options": "Observed"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIso"}]}]),

    timeseries("Daily average temperature, since Jan 2025", 0, 22, 12, 9, CITY_TEMP_TREND,
               unit="celsius", decimals=1, fill=0, colors=CITY_COLORS, legend="right"),
    timeseries("Daily average wind speed", 12, 22, 12, 9, CITY_WIND_TREND,
               unit="velocitykmh", decimals=0, fill=0, colors=CITY_COLORS, legend="right"),

    timeseries("Daily average humidity", 0, 31, 12, 9, CITY_HUMIDITY_TREND, unit="humidity",
               decimals=0, fill=0, colors=CITY_COLORS, legend="right"),
    timeseries("Daily total rainfall", 12, 31, 12, 9, CITY_RAIN_TREND, unit="lengthmm",
               decimals=1, fill=40, lw=1, colors=CITY_COLORS, legend="right"),

    timeseries("Daily average air quality (European AQI)", 0, 40, 24, 9, CITY_AQI_TREND,
               decimals=0, fill=0, colors=CITY_COLORS, legend="right"),
]

write(dashboard("nl-weather", "NL: Weather & Air Quality", panels, ["netherlands"],
                refresh="15m", time_from="2025-01-01T00:00:00Z",
                description="Weather and air quality for 5 Dutch cities, since 2025."),
      "NL/nl-weather")

from _lib import CAT, DS, dashboard, gauge, stat, table, target, timeseries, barchart, write

CITY_VAR = {
    "name": "city", "label": "City", "type": "query", "datasource": DS,
    "query": "SELECT city FROM city ORDER BY city", "definition": "SELECT city FROM city ORDER BY city",
    "refresh": 1, "includeAll": False, "multi": False, "sort": 1,
    "current": {"text": "Istanbul", "value": "Istanbul"},
    "options": [], "hide": 0,
}

def now_col(col):
    return f"""SELECT ts AS time, {col} FROM weather_current WHERE city = '${{city}}' AND ts > now() - interval '24 hours' ORDER BY ts"""

CURRENT_LINES = """
SELECT ts AS time, temp_c AS "Temperature", feels_like_c AS "Feels like"
FROM weather_current WHERE city='${city}' AND $__timeFilter(ts) ORDER BY 1
"""
HUM_CLOUD = """
SELECT ts AS time, humidity AS "Humidity %", cloud_pct AS "Cloud cover %"
FROM weather_current WHERE city='${city}' AND $__timeFilter(ts) ORDER BY 1
"""
WIND = """
SELECT ts AS time, wind_kph AS "Wind km/h" FROM weather_current WHERE city='${city}' AND $__timeFilter(ts) ORDER BY 1
"""
PRESSURE = """
SELECT ts AS time, pressure_hpa AS "Pressure hPa" FROM weather_current WHERE city='${city}' AND $__timeFilter(ts) ORDER BY 1
"""
AQ = """
SELECT ts AS time, aqi_eu AS "European AQI", pm2_5 AS "PM2.5", pm10 AS "PM10"
FROM weather_current WHERE city='${city}' AND $__timeFilter(ts) ORDER BY 1
"""
FORECAST = """
SELECT to_char(day, 'Dy DD') AS "Day", tmin_c AS "Min °C", tmax_c AS "Max °C", precip_mm AS "Rain mm", precip_prob AS "Rain %"
FROM weather_forecast WHERE city='${city}' AND day >= current_date ORDER BY day
"""
FORECAST_BARS = """
SELECT day AS time, tmin_c AS "Min °C", tmax_c AS "Max °C"
FROM weather_forecast WHERE city='${city}' AND day >= current_date ORDER BY day
"""
HISTORY = """
SELECT day AS time, tmin_c AS "Min °C", tmax_c AS "Max °C"
FROM weather_daily WHERE city='${city}' AND $__timeFilter(day) ORDER BY 1
"""
HISTORY_RAIN = """
SELECT day AS time, precip_mm AS "Rain mm" FROM weather_daily WHERE city='${city}' AND $__timeFilter(day) ORDER BY 1
"""
ALL_CITIES_TEMP = """
SELECT $__timeGroupAlias(ts, '1h'), city AS metric, avg(temp_c) AS value
FROM weather_current WHERE $__timeFilter(ts) GROUP BY 1, 2 ORDER BY 1
"""
WEATHER_CODE = """
SELECT CASE weather_code
  WHEN 0 THEN 'Clear sky' WHEN 1 THEN 'Mainly clear' WHEN 2 THEN 'Partly cloudy' WHEN 3 THEN 'Overcast'
  WHEN 45 THEN 'Fog' WHEN 48 THEN 'Rime fog' WHEN 51 THEN 'Light drizzle' WHEN 53 THEN 'Drizzle' WHEN 55 THEN 'Dense drizzle'
  WHEN 61 THEN 'Slight rain' WHEN 63 THEN 'Rain' WHEN 65 THEN 'Heavy rain' WHEN 66 THEN 'Freezing rain' WHEN 67 THEN 'Heavy freezing rain'
  WHEN 71 THEN 'Slight snow' WHEN 73 THEN 'Snow' WHEN 75 THEN 'Heavy snow' WHEN 77 THEN 'Snow grains'
  WHEN 80 THEN 'Rain showers' WHEN 81 THEN 'Heavy showers' WHEN 82 THEN 'Violent showers'
  WHEN 85 THEN 'Snow showers' WHEN 86 THEN 'Heavy snow showers' WHEN 95 THEN 'Thunderstorm' WHEN 96 THEN 'Thunderstorm, hail' WHEN 99 THEN 'Thunderstorm, heavy hail'
  ELSE 'Unknown' END AS sky
FROM weather_current WHERE city='${city}' ORDER BY ts DESC LIMIT 1
"""

panels = [
    stat("Temperature", 0, 0, 4, 4, now_col("temp_c"), unit="celsius", decimals=1, color=CAT[1]),
    stat("Feels like", 4, 0, 4, 4, now_col("feels_like_c"), unit="celsius", decimals=1, color=CAT[3]),
    stat("Sky", 8, 0, 4, 4, WEATHER_CODE, sparkline=False, color_mode="none", text_value=True),
    stat("Humidity", 12, 0, 3, 4, now_col("humidity"), unit="humidity", decimals=0, color=CAT[0]),
    stat("Wind", 15, 0, 3, 4, now_col("wind_kph"), unit="velocitykmh", decimals=0, color=CAT[2]),
    stat("Pressure", 18, 0, 3, 4, now_col("pressure_hpa"), unit="pressurehpa", decimals=0, color=CAT[6]),
    gauge("Air quality (EU AQI)", 21, 0, 3, 4, now_col("aqi_eu"), min_=0, max_=100,
          steps=[{"color": "#0ca30c", "value": None}, {"color": "#fab219", "value": 40}, {"color": "#ec835a", "value": 60}, {"color": "#d03b3b", "value": 80}]),

    timeseries("Temperature and feels-like", 0, 4, 12, 9, CURRENT_LINES, unit="celsius", decimals=1, colors={"Temperature": CAT[1], "Feels like": CAT[3]}),
    barchart("7-day forecast, min / max °C", 12, 4, 12, 9, FORECAST_BARS, unit="celsius", horizontal=False, colors_by_field={"Min °C": CAT[0], "Max °C": CAT[1]}, legend="bottom", decimals=0),

    timeseries("Humidity and cloud cover", 0, 13, 8, 8, HUM_CLOUD, unit="percent", decimals=0, colors={"Humidity %": CAT[0], "Cloud cover %": CAT[7]}, max_=100, min_=0),
    timeseries("Wind", 8, 13, 8, 8, WIND, unit="velocitykmh", decimals=0, colors={"Wind km/h": CAT[2]}),
    timeseries("Pressure", 16, 13, 8, 8, PRESSURE, unit="pressurehpa", decimals=0, colors={"Pressure hPa": CAT[6]}, fill=0),

    timeseries("Air quality", 0, 21, 12, 8, AQ, decimals=0, colors={"European AQI": CAT[5], "PM2.5": CAT[4], "PM10": CAT[6]}, fill=0),
    table("Forecast", 12, 21, 12, 8, FORECAST,
          overrides=[{"matcher": {"id": "byName", "options": "Max °C"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
                                     {"id": "color", "value": {"mode": "continuous-BlYlRd"}}, {"id": "min", "value": -10}, {"id": "max", "value": 40}]},
                     {"matcher": {"id": "byName", "options": "Min °C"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
                                     {"id": "color", "value": {"mode": "continuous-BlYlRd"}}, {"id": "min", "value": -10}, {"id": "max", "value": 40}]},
                     {"matcher": {"id": "byName", "options": "Rain %"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}}, {"id": "min", "value": 0}, {"id": "max", "value": 100}, {"id": "color", "value": {"mode": "fixed", "fixedColor": CAT[0]}}]}]),

    timeseries("Daily min / max, past year (ERA5 archive + recent forecast days)", 0, 29, 16, 9, HISTORY, unit="celsius", decimals=0, colors={"Min °C": CAT[0], "Max °C": CAT[1]}, fill=15),
    timeseries("Daily rain, past year", 16, 29, 8, 9, HISTORY_RAIN, unit="lengthmm", decimals=1, colors={"Rain mm": CAT[0]}, fill=60, lw=1),
    timeseries("All cities — hourly temperature", 0, 38, 24, 10, ALL_CITIES_TEMP, unit="celsius", decimals=0, fill=0, legend="right", lw=1,
               description="21 cities on one axis. Click a legend entry to isolate."),
]

write(dashboard("city-weather", "City Weather", panels, ["weather"], refresh="5m", time_from="now-7d",
                templating=[CITY_VAR],
                description="Current conditions, forecast, air quality and a year of history for one city."),
      "city-weather")

from _lib import CAT, dashboard, stat, timeseries, write

DK_WIND_SOLAR = """
SELECT ts AS time, region || ' ' || indicator AS metric, value FROM energy_grid
WHERE source='energidataservice' AND indicator IN ('wind_generation_mwh', 'solar_generation_mwh')
  AND $__timeFilter(ts)
ORDER BY 1
"""

DK_CONSUMPTION = """
SELECT ts AS time, region AS metric, value FROM energy_grid
WHERE source='energidataservice' AND indicator='gross_consumption_mwh' AND $__timeFilter(ts)
ORDER BY 1
"""

UK_CARBON_INTENSITY = """
SELECT ts AS time, indicator AS metric, value FROM energy_grid
WHERE source='carbonintensity.org.uk' AND $__timeFilter(ts)
ORDER BY 1
"""

panels = [
    stat("DK1 wind generation, latest hour", 0, 0, 6, 4,
         "SELECT value FROM energy_grid WHERE region='DK1' AND indicator='wind_generation_mwh' "
         "ORDER BY ts DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[0]),
    stat("DK2 wind generation, latest hour", 6, 0, 6, 4,
         "SELECT value FROM energy_grid WHERE region='DK2' AND indicator='wind_generation_mwh' "
         "ORDER BY ts DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[0]),
    stat("GB carbon intensity", 12, 0, 6, 4,
         "SELECT value FROM energy_grid WHERE region='GB' "
         "AND indicator='carbon_intensity_gco2_kwh' ORDER BY ts DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[2], description="gCO2/kWh, actual."),
    stat("GB carbon intensity, forecast", 18, 0, 6, 4,
         "SELECT value FROM energy_grid WHERE region='GB' "
         "AND indicator='carbon_intensity_forecast_gco2_kwh' ORDER BY ts DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[3]),

    timeseries("Denmark: wind & solar generation by price area", 0, 4, 24, 10, DK_WIND_SOLAR,
               unit="short", decimals=0, fill=0, legend="right",
               colors={"DK1 wind_generation_mwh": CAT[0], "DK1 solar_generation_mwh": CAT[3],
                       "DK2 wind_generation_mwh": CAT[1], "DK2 solar_generation_mwh": CAT[4]},
               description="Energi Data Service, hourly, runs a few days behind real "
                           "time (settlement lag) — not a live feed."),
    timeseries("Denmark: gross consumption by price area", 0, 14, 24, 9, DK_CONSUMPTION,
               unit="short", decimals=0, colors={"DK1": CAT[0], "DK2": CAT[1]}, fill=15),

    timeseries("Great Britain: grid carbon intensity, actual vs. forecast", 0, 23, 24, 9,
               UK_CARBON_INTENSITY, unit="short", decimals=0,
               colors={"carbon_intensity_gco2_kwh": CAT[2],
                       "carbon_intensity_forecast_gco2_kwh": CAT[6]},
               fill=0, points=True,
               description="National Grid ESO, 30-minute settlement periods."),
]

write(dashboard("global-energy-grid", "Global: Energy Grid", panels, ["global"], refresh="30m",
                time_from="now-30d",
                description="Live electricity grid data: Denmark's wind/solar/"
                            "conventional generation mix and consumption by price area "
                            "(Energi Data Service), and Great Britain's grid carbon "
                            "intensity, actual + forecast (National Grid ESO)."),
      "global-energy-grid")

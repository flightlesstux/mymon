from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

FLEET_BY_FUEL = nl_multi(
    ["vehicle_fleet_petrol", "vehicle_fleet_diesel", "vehicle_fleet_lpg",
     "vehicle_fleet_electric", "vehicle_fleet_cng"], "cbs"
)
FUEL_COLORS = {
    "vehicle_fleet_petrol": CAT[0], "vehicle_fleet_diesel": CAT[3],
    "vehicle_fleet_lpg": CAT[4], "vehicle_fleet_electric": CAT[2],
    "vehicle_fleet_cng": CAT[6],
}

FUEL_SHARE_PCT = """
SELECT p.period_date AS time, p.indicator AS metric,
       round((100 * p.value / NULLIF(total.value, 0))::numeric, 2) AS value
FROM price_index p
JOIN (SELECT period_date, value FROM price_index
      WHERE country_iso3='NLD' AND source='cbs' AND indicator='vehicle_fleet_total') total
  ON total.period_date = p.period_date
WHERE p.country_iso3='NLD' AND p.source='cbs'
  AND p.indicator IN ('vehicle_fleet_petrol','vehicle_fleet_diesel','vehicle_fleet_lpg',
                       'vehicle_fleet_electric','vehicle_fleet_cng')
  AND $__timeFilter(p.period_date)
ORDER BY 1
"""

panels = [
    stat("Total passenger cars", 0, 0, 5, 4, nl_latest("vehicle_fleet_total", "cbs"),
         unit="short", decimals=0, color=CAT[0]),
    stat("Petrol", 5, 0, 4, 4, nl_latest("vehicle_fleet_petrol", "cbs"),
         unit="short", decimals=0, color=CAT[0]),
    stat("Diesel", 9, 0, 4, 4, nl_latest("vehicle_fleet_diesel", "cbs"),
         unit="short", decimals=0, color=CAT[3]),
    stat("Electric", 13, 0, 4, 4, nl_latest("vehicle_fleet_electric", "cbs"),
         unit="short", decimals=0, color=CAT[2],
         description="From 40 cars in 2000 to this today."),
    stat("LPG", 17, 0, 3, 4, nl_latest("vehicle_fleet_lpg", "cbs"),
         unit="short", decimals=0, color=CAT[4]),
    stat("CNG", 20, 0, 4, 4, nl_latest("vehicle_fleet_cng", "cbs"),
         unit="short", decimals=0, color=CAT[6]),

    timeseries("Passenger car fleet by fuel type", 0, 4, 24, 10, FLEET_BY_FUEL, unit="short",
               decimals=0, colors=FUEL_COLORS, fill=0, legend="right",
               description="CBS 71405ned (2000-2022) + 85237NED (2019-2026), stock as "
                           "of 1 January each year — not new sales; CBS doesn't publish "
                           "a fuel-type breakdown of new registrations."),
    timeseries("Fuel type share of fleet", 0, 14, 24, 10, FUEL_SHARE_PCT, unit="percent",
               decimals=1, colors=FUEL_COLORS, fill=15, stack=True, legend="right",
               description="Same data as a share of the total fleet each year."),

    stat("Marinas, latest survey", 0, 24, 6, 4,
         "SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
         "AND indicator='marina_count' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[1]),
    stat("Summer berths", 6, 24, 6, 4,
         "SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
         "AND indicator='marina_berths' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[6]),
    stat("Visitor overnight stays", 12, 24, 6, 4,
         "SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
         "AND indicator='marina_visitor_overnight_stays' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[2]),
    stat("Marina employees", 18, 24, 6, 4,
         "SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
         "AND indicator='marina_employees' ORDER BY period_date DESC LIMIT 1",
         unit="short", decimals=0, color=CAT[5]),

    timeseries("Marina capacity", 0, 28, 12, 9, nl_multi(["marina_count", "marina_berths"], "cbs"),
               unit="short", decimals=0, colors={"marina_count": CAT[1], "marina_berths": CAT[6]},
               fill=0, points=True,
               description="CBS 84133NED — irregular survey years (2015/2018/2020/2021), "
                           "discontinued after 2021. Two very different scales on one "
                           "axis (hundreds of marinas vs. tens of thousands of berths) — "
                           "use the legend, not the axis, to read each series."),
    timeseries("Marina employment & revenue", 12, 28, 12, 9,
               nl_multi(["marina_employees", "marina_revenue_mln_eur"], "cbs"),
               decimals=0, colors={"marina_employees": CAT[5],
                                    "marina_revenue_mln_eur": CAT[2]},
               fill=0, points=True,
               description="CBS 84132NED — every 2-3 years, 1997-2021."),
]

write(dashboard("nl-vehicles", "NL: Vehicles & Marinas", panels, ["netherlands"], refresh="1h",
                time_from="2000-01-01T00:00:00Z",
                description="Dutch passenger-car fleet by fuel type (petrol/diesel/"
                            "LPG/electric/CNG), since 2000, plus marina/yacht harbour "
                            "capacity and finances, survey years 1997-2021."),
      "NL/nl-vehicles")

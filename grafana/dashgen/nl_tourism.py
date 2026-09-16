from _lib import CAT, dashboard, barchart, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

TOURISM = nl_multi(["tourism_guests_thousands", "tourism_overnight_stays_thousands"], "cbs")

panels = [
    stat("Guests, latest month", 0, 0, 6, 4, nl_latest("tourism_guests_thousands", "cbs"),
         unit="short", decimals=0, color=CAT[0],
         description="Thousands of guests, all accommodation types."),
    stat("Overnight stays, latest month", 6, 0, 6, 4,
         nl_latest("tourism_overnight_stays_thousands", "cbs"),
         unit="short", decimals=0, color=CAT[4],
         description="Thousands of nights, all accommodation types."),
    stat("Hotel occupancy rate", 12, 0, 6, 4, nl_latest("tourism_occupancy_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[2]),
    stat("Avg. stay length", 18, 0, 6, 4,
         "SELECT g.period_date AS time, s.value / NULLIF(g.value, 0) AS value "
         "FROM price_index g JOIN price_index s "
         "  ON s.period_date = g.period_date AND s.country_iso3 = g.country_iso3 "
         "WHERE g.country_iso3='NLD' AND g.source='cbs' AND g.indicator='tourism_guests_thousands' "
         "  AND s.source='cbs' AND s.indicator='tourism_overnight_stays_thousands' "
         "ORDER BY g.period_date DESC LIMIT 1",
         decimals=2, color=CAT[6], description="Overnight stays per guest."),

    timeseries("Guests and overnight stays (thousands)", 0, 4, 12, 9, TOURISM, unit="short",
               decimals=0, colors={"tourism_guests_thousands": CAT[0],
                                    "tourism_overnight_stays_thousands": CAT[4]}, fill=0),
    timeseries("Hotel occupancy rate", 12, 4, 12, 9, nl("tourism_occupancy_pct", "cbs"),
               unit="percent", decimals=1, colors={"value": CAT[2]}, fill=15,
               description="Peaks in summer — a normal seasonal pattern, not an anomaly."),

    barchart("Overnight stays per month (thousands)", 0, 13, 24, 10,
             nl("tourism_overnight_stays_thousands", "cbs"), unit="short", color=CAT[4],
             horizontal=False),
]

write(dashboard("nl-tourism", "NL: Tourism", panels, ["mymon", "netherlands"], refresh="1h",
                time_from="2025-01-01T00:00:00Z",
                description="Dutch hotel/accommodation guests, overnight stays and "
                            "occupancy rate, since 2025."),
      "NL/nl-tourism")

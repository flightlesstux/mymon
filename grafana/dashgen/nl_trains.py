from _lib import CAT, dashboard, stat, write

panels = [
    stat("NS active train disruptions", 0, 0, 12, 6,
         "SELECT period_date AS time, value FROM price_index WHERE country_iso3='NLD' "
         "AND indicator='ns_disruptions_active' AND source='ns' "
         "ORDER BY period_date DESC LIMIT 1",
         decimals=0, color=CAT[1],
         description="Live-only (no historical API); shows 'No data' until NS_API_KEY is "
                     "set — free instant signup at apiportal.ns.nl."),
    stat("...of which unplanned (STORING)", 12, 0, 12, 6,
         "SELECT period_date AS time, value FROM price_index WHERE country_iso3='NLD' "
         "AND indicator='ns_disruptions_unplanned' AND source='ns' "
         "ORDER BY period_date DESC LIMIT 1",
         decimals=0, color=CAT[7]),
]

write(dashboard("nl-trains", "NL: Trains", panels, ["netherlands"], refresh="15m",
                time_from="now-24h",
                description="NS (Dutch Railways) active disruption count. Needs NS_API_KEY "
                            "(free instant signup, apiportal.ns.nl) — live only, no "
                            "historical query API exists, so not backfillable."),
      "NL/nl-trains")

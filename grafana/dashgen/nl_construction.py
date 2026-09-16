from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

BUILDING_COST_INPUT = nl_multi(
    ["building_cost_input_wage_index", "building_cost_input_material_index"], "cbs"
)
BUILDING_COST_OUTPUT = nl_multi(
    ["building_cost_output_index_incl_vat", "building_cost_output_index_excl_vat"], "cbs"
)
PERMITS = nl_multi(["building_permits_count"], "cbs")

SECTOR_SLUGS = {
    "agriculture": "Agriculture", "industry": "Industry", "construction": "Construction",
    "trade": "Trade", "transport": "Transport", "hospitality": "Hospitality", "ict": "ICT",
    "finance": "Finance", "real_estate": "Real estate", "business_services": "Business services",
    "other_business_services": "Other business services", "healthcare": "Healthcare",
    "culture_sport_recreation": "Culture, sport & recreation",
}
SECTOR_COLORS = {label: CAT[i % len(CAT)] for i, label in enumerate(SECTOR_SLUGS.values())}

BANKRUPTCIES_BY_SECTOR = f"""
SELECT period_date AS time,
       CASE indicator
         {" ".join(f"WHEN 'bankruptcies_sector_{slug}' THEN '{label}'" for slug, label in SECTOR_SLUGS.items())}
         ELSE indicator
       END AS metric, value
FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ({",".join(f"'bankruptcies_sector_{slug}'" for slug in SECTOR_SLUGS)})
  AND $__timeFilter(period_date)
ORDER BY 1
"""

BANKRUPTCIES_LATEST_BY_SECTOR = f"""
SELECT DISTINCT ON (indicator)
       CASE indicator
         {" ".join(f"WHEN 'bankruptcies_sector_{slug}' THEN '{label}'" for slug, label in SECTOR_SLUGS.items())}
         ELSE indicator
       END AS "Sector", value AS "Bankruptcies", period_date AS "Month"
FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ({",".join(f"'bankruptcies_sector_{slug}'" for slug in SECTOR_SLUGS)})
ORDER BY indicator, period_date DESC
"""

panels = [
    stat("Construction turnover index", 0, 0, 5, 4, nl_latest("construction_turnover_index", "cbs"),
         decimals=1, color=CAT[0]),
    stat("Turnover, YoY", 5, 0, 5, 4, nl_latest("construction_turnover_yoy_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[2]),
    stat("Building permits, latest month", 10, 0, 5, 4, nl_latest("building_permits_count", "cbs"),
         unit="short", decimals=0, color=CAT[3]),
    stat("Business bankruptcies, latest month", 15, 0, 5, 4, nl_latest("bankruptcies_total", "cbs"),
         unit="short", decimals=0, color=CAT[7]),
    stat("Building cost, output index", 20, 0, 4, 4,
         nl_latest("building_cost_output_index_incl_vat", "cbs"),
         decimals=1, color=CAT[1], description="2000=100. Series runs back to 1914."),

    timeseries("Construction sector turnover index", 0, 4, 24, 9,
               nl("construction_turnover_index", "cbs"), decimals=1,
               colors={"value": CAT[0]}, fill=15, description="CBS 85809NED, since 2009."),

    timeseries("Building cost, input (wage vs. material component)", 0, 13, 12, 9,
               BUILDING_COST_INPUT, decimals=1,
               colors={"building_cost_input_wage_index": CAT[1],
                       "building_cost_input_material_index": CAT[3]}, fill=0,
               description="CBS 80444ned, monthly since 1990."),
    timeseries("Building cost, output (incl. vs. excl. VAT)", 12, 13, 12, 9,
               BUILDING_COST_OUTPUT, decimals=1,
               colors={"building_cost_output_index_incl_vat": CAT[0],
                       "building_cost_output_index_excl_vat": CAT[6]}, fill=0,
               description="CBS 80334ned, annual since 1914 — the deepest history of "
                           "any series in this project."),

    timeseries("Building permits issued", 0, 22, 24, 9, PERMITS, unit="short", decimals=0,
               colors={"building_permits_count": CAT[3]}, fill=15,
               description="CBS 83667NED, monthly since 2012, all work types & "
                           "building purposes combined."),

    timeseries("Business bankruptcies", 0, 31, 24, 9, nl("bankruptcies_total", "cbs"),
               unit="short", decimals=0, colors={"value": CAT[7]}, fill=40, lw=1,
               description="CBS 82242NED, monthly since 1981 — companies and "
                           "institutions only, not natural persons."),

    timeseries("Bankruptcies by sector", 0, 40, 24, 10, BANKRUPTCIES_BY_SECTOR, unit="short",
               decimals=0, colors=SECTOR_COLORS, fill=0, legend="right",
               description="CBS 82244NED, 13 top-level SBI sectors, monthly since 2009."),
]

write(dashboard("nl-construction", "NL: Construction & Bankruptcies", panels, ["netherlands"],
                refresh="1h", time_from="1990-01-01T00:00:00Z",
                description="Dutch construction sector turnover, building costs "
                            "(back to 1914), building permits, and business "
                            "bankruptcies economy-wide and by 13 sectors."),
      "NL/nl-construction")

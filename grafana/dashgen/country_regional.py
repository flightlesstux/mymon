"""One dashboard generator, six countries — NUTS2 regional breakdown (unemployment, GDP
per capita, population) from eurostat_regional.py. Region codes are looked up to names
via _eurostat_common.REGION_LABELS rather than joined against a region table (there's no
NUTS2 region table in this schema, unlike NL's province-level region/region_metric
tables) — same plain CASE-WHEN pattern nl_grocery_prices.py and country_cost_of_living.py
already use for their own label lookups.
"""

import _lib
from _lib import CAT, barchart, dashboard, table, write
from _eurostat_common import REGION_LABELS

COUNTRIES = [
    ("DE", "DEU", "Germany"),
    ("IT", "ITA", "Italy"),
    ("ES", "ESP", "Spain"),
    ("GR", "GRC", "Greece"),
    ("TR", "TUR", "Turkey"),
    ("FR", "FRA", "France"),
]

# Eurostat's NUTS geo prefix differs from our own display code only for Greece (EL, not
# GR) — same quirk as every other Eurostat module in this project.
GEO_PREFIX = {"GR": "EL"}


def _region_label_case(prefix: str, column: str) -> str:
    codes = {code: label for code, label in REGION_LABELS.items() if code.startswith(prefix)}
    whens = " ".join(f"WHEN '{code}' THEN '{label}'" for code, label in codes.items())
    return f"CASE {column} {whens} ELSE {column} END"


for code, iso3, name in COUNTRIES:
    _lib._id = 0
    prefix = GEO_PREFIX.get(code, code)
    region_case = _region_label_case(prefix, "right(indicator, 4)")

    unemployment_bar = f"""
    SELECT {region_case} AS "Region", value AS "Unemployment %"
    FROM (
        SELECT DISTINCT ON (indicator) indicator, value
        FROM price_index
        WHERE country_iso3='{iso3}' AND source='eurostat'
          AND indicator LIKE 'regional_unemployment_pct_{prefix}%'
        ORDER BY indicator, period_date DESC
    ) latest
    ORDER BY value DESC
    """

    summary_table = f"""
    SELECT {region_case} AS "Region",
           MAX(CASE WHEN indicator LIKE 'regional_unemployment_pct_%' THEN value END) AS "Unemployment %",
           MAX(CASE WHEN indicator LIKE 'regional_gdp_per_capita_eur_%' THEN value END) AS "GDP per capita (EUR)",
           MAX(CASE WHEN indicator LIKE 'regional_population_%' THEN value END) AS "Population"
    FROM (
        SELECT DISTINCT ON (indicator) indicator, value
        FROM price_index
        WHERE country_iso3='{iso3}' AND source='eurostat'
          AND (indicator LIKE 'regional_unemployment_pct_{prefix}%'
               OR indicator LIKE 'regional_gdp_per_capita_eur_{prefix}%'
               OR indicator LIKE 'regional_population_{prefix}%')
        ORDER BY indicator, period_date DESC
    ) latest
    GROUP BY 1
    ORDER BY "GDP per capita (EUR)" DESC NULLS LAST
    """

    panels = [
        table(f"{name}: all NUTS2 regions, latest values", 0, 0, 24, 14, summary_table,
              sort=("GDP per capita (EUR)", True),
              description="One row per NUTS2 region (Eurostat's statistical region "
                          "level, roughly analogous to a US state or a large Dutch "
                          "province). Unemployment: lfst_r_lfu3rt. GDP per capita: "
                          "nama_10r_2gdp. Population: demo_r_pjangrp3."),
        barchart(f"{name}: unemployment rate by region, ranked", 0, 14, 24, 14,
                 unemployment_bar, unit="percent", decimals=1, color=CAT[2]),
    ]

    write(dashboard(f"{code.lower()}-regional", f"{name}: Regions", panels,
                    [name.lower()], refresh="1h",
                    description=f"{name} broken down by NUTS2 region: unemployment "
                                f"rate, GDP per capita and population, via Eurostat."),
          f"{code}/{code.lower()}-regional")

"""NL: Safety — recorded crime rate by offence category and road deaths, from
eurostat_safety.py. Mirrors country_safety.py's DE/IT/ES/GR/TR/FR dashboards; nothing
safety-related existed for the Netherlands before this either.
"""

from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest
from _eurostat_common import CRIME_LABELS

CRIME_WHENS = " ".join(
    f"WHEN 'crime_rate_per_100k_{k}' THEN '{label}'" for k, label in CRIME_LABELS.items()
)
CRIME_INLIST = ",".join(f"'crime_rate_per_100k_{k}'" for k in CRIME_LABELS)
CRIME_TREND = f"""
SELECT period_date AS time, CASE indicator {CRIME_WHENS} ELSE indicator END AS metric, value
FROM price_index
WHERE country_iso3='NLD' AND source='eurostat' AND indicator IN ({CRIME_INLIST})
  AND $__timeFilter(period_date) ORDER BY 1
"""
CRIME_COLORS = {label: CAT[i % len(CAT)] for i, label in enumerate(CRIME_LABELS.values())}

panels = [
    stat("Homicide rate, per 100k, latest", 0, 0, 8, 4,
         nl_latest("crime_rate_per_100k_homicide", "eurostat"), decimals=2, color=CAT[7]),
    stat("Theft rate, per 100k, latest", 8, 0, 8, 4,
         nl_latest("crime_rate_per_100k_theft", "eurostat"), decimals=1, color=CAT[3]),
    stat("Road deaths, per million, latest", 16, 0, 8, 4,
         nl_latest("road_deaths_per_million", "eurostat"), decimals=1, color=CAT[0]),

    timeseries("Netherlands: recorded crime rate by offence (per 100,000 inhabitants)",
               0, 4, 24, 14, CRIME_TREND, decimals=2, colors=CRIME_COLORS, fill=0,
               legend="right", points=True,
               description="Eurostat crim_off_cat, harmonized ICCS offence "
                           "categories, annual since 2008."),

    timeseries("Road deaths (per million inhabitants)", 0, 18, 24, 9,
               nl("road_deaths_per_million", "eurostat"), decimals=1,
               colors={"value": CAT[0]}, fill=15,
               description="Eurostat tran_r_acci, annual since 1990."),
]

write(dashboard("nl-safety", "NL: Safety", panels, ["netherlands"], refresh="1h",
                time_from="2000-01-01T00:00:00Z",
                description="Dutch recorded crime rate by offence category and road "
                            "deaths — via Eurostat."),
      "NL/nl-safety")

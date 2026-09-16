"""One dashboard generator, six countries — recorded crime rate by offence category and
road deaths, from eurostat_safety.py. Nothing safety-related existed before this.
"""

import _lib
from _lib import CAT, dashboard, stat, timeseries, write
from _eurostat_common import CRIME_LABELS

COUNTRIES = [
    ("DE", "DEU", "Germany"),
    ("IT", "ITA", "Italy"),
    ("ES", "ESP", "Spain"),
    ("GR", "GRC", "Greece"),
    ("TR", "TUR", "Turkey"),
    ("FR", "FRA", "France"),
]

RANGE_START = "2000-01-01"
CRIME_COLORS = {label: CAT[i % len(CAT)] for i, label in enumerate(CRIME_LABELS.values())}


def q(country_iso3: str, indicator: str) -> str:
    return (
        f"SELECT period_date AS time, value FROM price_index "
        f"WHERE country_iso3='{country_iso3}' AND indicator='{indicator}' AND source='eurostat' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


def q_latest(country_iso3: str, indicator: str) -> str:
    return (
        f"SELECT value FROM price_index WHERE country_iso3='{country_iso3}' "
        f"AND indicator='{indicator}' AND source='eurostat' ORDER BY period_date DESC LIMIT 1"
    )


def _label_case(column: str) -> str:
    whens = " ".join(
        f"WHEN 'crime_rate_per_100k_{k}' THEN '{label}'" for k, label in CRIME_LABELS.items()
    )
    return f"CASE {column} {whens} ELSE {column} END"


for code, iso3, name in COUNTRIES:
    _lib._id = 0

    inlist = ",".join(f"'crime_rate_per_100k_{k}'" for k in CRIME_LABELS)
    crime_trend = f"""
    SELECT period_date AS time, {_label_case("indicator")} AS metric, value
    FROM price_index
    WHERE country_iso3='{iso3}' AND source='eurostat' AND indicator IN ({inlist})
      AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date)
    ORDER BY 1
    """

    panels = [
        stat("Homicide rate, per 100k, latest", 0, 0, 8, 4,
             q_latest(iso3, "crime_rate_per_100k_homicide"), decimals=2, color=CAT[7]),
        stat("Theft rate, per 100k, latest", 8, 0, 8, 4,
             q_latest(iso3, "crime_rate_per_100k_theft"), decimals=1, color=CAT[3]),
        stat("Road deaths, per million, latest", 16, 0, 8, 4,
             q_latest(iso3, "road_deaths_per_million"), decimals=1, color=CAT[0]),

        timeseries(f"{name}: recorded crime rate by offence (per 100,000 inhabitants)",
                   0, 4, 24, 14, crime_trend, decimals=2, colors=CRIME_COLORS, fill=0,
                   legend="right", points=True,
                   description="Eurostat crim_off_cat, harmonized ICCS offence "
                               "categories, annual since 2008. Not every category is "
                               "reported by every country every year."),

        timeseries("Road deaths (per million inhabitants)", 0, 18, 24, 9,
                   q(iso3, "road_deaths_per_million"),
                   decimals=1, colors={"value": CAT[0]}, fill=15,
                   description="Eurostat tran_r_acci, annual since 1990."),
    ]

    write(dashboard(f"{code.lower()}-safety", f"{name}: Safety", panels,
                    [name.lower()], refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name}: recorded crime rate by offence category and "
                                f"road deaths — via Eurostat."),
          f"{code}/{code.lower()}-safety")

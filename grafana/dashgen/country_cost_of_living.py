"""One dashboard generator, six countries — CPI broken into all 12 COICOP categories,
from eurostat_cost_of_living.py. Mirrors NL: Cost of Living.
"""

import _lib
from _lib import CAT, dashboard, timeseries, write
from _eurostat_common import COST_OF_LIVING_LABELS

COUNTRIES = [
    ("DE", "DEU", "Germany"),
    ("IT", "ITA", "Italy"),
    ("ES", "ESP", "Spain"),
    ("GR", "GRC", "Greece"),
    ("TR", "TUR", "Turkey"),
    ("FR", "FRA", "France"),
]

CAT_KEYS = list(COST_OF_LIVING_LABELS)
CAT_COLORS = {label: CAT[i % len(CAT)] for i, label in enumerate(COST_OF_LIVING_LABELS.values())}
RANGE_START = "2000-01-01"


def _label_case(column: str) -> str:
    whens = " ".join(
        f"WHEN 'cpi_cat_{k}' THEN '{label}'" for k, label in COST_OF_LIVING_LABELS.items()
    )
    return f"CASE {column} {whens} ELSE {column} END"


for code, iso3, name in COUNTRIES:
    _lib._id = 0

    inlist = ",".join(f"'cpi_cat_{k}'" for k in CAT_KEYS)
    category_trend = f"""
    SELECT period_date AS time, {_label_case("indicator")} AS metric, value
    FROM price_index
    WHERE country_iso3='{iso3}' AND source='eurostat' AND indicator IN ({inlist})
      AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date)
    ORDER BY 1
    """

    panels = [
        timeseries(f"{name}: CPI by spending category (2015=100)", 0, 0, 24, 16,
                   category_trend, decimals=1, colors=CAT_COLORS, fill=0, legend="right",
                   description="All 12 top-level COICOP categories Eurostat splits "
                               "the CPI into."),
    ]

    write(dashboard(f"{code.lower()}-cost-of-living", f"{name}: Cost of Living", panels,
                    [name.lower()], refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name} consumer prices broken down into all 12 "
                                f"COICOP spending categories (Eurostat), since 2000 "
                                f"where the data goes back that far."),
          f"{code}/{code.lower()}-cost-of-living")

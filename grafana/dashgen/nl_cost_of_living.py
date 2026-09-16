from _lib import CAT, dashboard, barchart, table, timeseries, write
from _nl_common import CPI_CATEGORY_LABELS, RANGE_START

CAT_KEYS = list(CPI_CATEGORY_LABELS)
CAT_INLIST = ",".join(f"'cpi_cat_{k}'" for k in CAT_KEYS)
# fixed color per category (by label, since that's what ends up as the series/metric name
# in every panel below) so the legend stays stable across all three panels
CAT_COLORS = {label: CAT[i % len(CAT)] for i, label in enumerate(CPI_CATEGORY_LABELS.values())}


def _label_case(column: str) -> str:
    whens = " ".join(
        f"WHEN 'cpi_cat_{k}' THEN '{label}'" for k, label in CPI_CATEGORY_LABELS.items()
    )
    return f"CASE {column} {whens} ELSE {column} END"


CATEGORY_TREND = f"""
SELECT period_date AS time, {_label_case("indicator")} AS metric, value
FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ({CAT_INLIST})
  AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date)
ORDER BY 1
"""

CHANGE_SINCE_2025 = f"""
WITH bounds AS (
  SELECT indicator,
    (array_agg(value ORDER BY period_date ASC))[1] AS first_value,
    (array_agg(value ORDER BY period_date DESC))[1] AS last_value
  FROM price_index
  WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ({CAT_INLIST})
    AND period_date >= '{RANGE_START}'
  GROUP BY indicator
)
SELECT {_label_case("indicator")} AS "Category",
       round((100 * (last_value / NULLIF(first_value, 0) - 1))::numeric, 2) AS "Change since Jan 2025, %"
FROM bounds
ORDER BY 2 DESC
"""

LATEST_TABLE = f"""
SELECT DISTINCT ON (indicator) {_label_case("indicator")} AS "Category",
       value AS "Index (2015=100)", period_date AS "Month"
FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ({CAT_INLIST})
ORDER BY indicator, period_date DESC
"""

panels = [
    timeseries("CPI by spending category (2015=100)", 0, 0, 24, 13, CATEGORY_TREND,
               decimals=1, colors={k: v for k, v in CAT_COLORS.items()}, fill=0, legend="right",
               description="All 12 top-level COICOP categories CBS splits the CPI into."),
    barchart("Change since Jan 2025, by category", 0, 13, 12, 12, CHANGE_SINCE_2025,
             unit="percent", color=CAT[1], decimals=2),
    table("Latest index value, by category", 12, 13, 12, 12, LATEST_TABLE,
          sort=("Index (2015=100)", True),
          overrides=[{"matcher": {"id": "byName", "options": "Month"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIsoNoDateIfToday"}]}]),
]

write(dashboard("nl-cost-of-living", "NL: Cost of Living", panels, ["netherlands"],
                refresh="1h", time_from="2025-01-01T00:00:00Z",
                description="Dutch consumer prices broken down into all 12 COICOP "
                            "spending categories (CBS), since 2025."),
      "NL/nl-cost-of-living")

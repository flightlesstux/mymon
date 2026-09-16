from _lib import CAT, dashboard, barchart, table, timeseries, write
from _nl_common import CPI_PRODUCT_LABELS, RANGE_START

PRODUCT_KEYS = list(CPI_PRODUCT_LABELS)


def _label_case(column: str) -> str:
    whens = " ".join(
        f"WHEN 'cpi_product_{k}' THEN '{label}'" for k, label in CPI_PRODUCT_LABELS.items()
    )
    return f"CASE {column} {whens} ELSE {column} END"


ALL_PRODUCTS_LATEST = f"""
SELECT DISTINCT ON (indicator) {_label_case("indicator")} AS "Product",
       value AS "Index (2015=100)", period_date AS "Month"
FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ({",".join(f"'cpi_product_{k}'" for k in PRODUCT_KEYS)})
ORDER BY indicator, period_date DESC
"""

YOY_LATEST = f"""
SELECT DISTINCT ON (indicator) {_label_case("replace(indicator, '_yoy', '')")} AS "Product",
       value AS "YoY %", period_date AS "Month"
FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ({",".join(f"'cpi_product_{k}_yoy'" for k in PRODUCT_KEYS)})
ORDER BY indicator, period_date DESC
"""

TOP_MOVERS = f"""
SELECT DISTINCT ON (indicator) {_label_case("replace(indicator, '_yoy', '')")} AS "Product",
       value AS "YoY %"
FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ({",".join(f"'cpi_product_{k}_yoy'" for k in PRODUCT_KEYS)})
ORDER BY indicator, period_date DESC
"""

PRODUCT_VAR = {
    "name": "product", "label": "Product", "type": "custom",
    "query": ",".join(f"{label} : {slug}" for slug, label in CPI_PRODUCT_LABELS.items()),
    "current": {"text": "Bread", "value": "bread"},
    "options": [
        {"text": label, "value": slug, "selected": slug == "bread"}
        for slug, label in CPI_PRODUCT_LABELS.items()
    ],
    "multi": False, "includeAll": False, "hide": 0,
}

PRODUCT_TREND = f"""
SELECT period_date AS time, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator='cpi_product_${{product}}'
  AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date)
ORDER BY 1
"""

panels = [
    table("Every tracked product, latest index value", 0, 0, 24, 16, ALL_PRODUCTS_LATEST,
          decimals=1, sort=("Index (2015=100)", True),
          overrides=[{"matcher": {"id": "byName", "options": "Month"},
                      "properties": [{"id": "unit", "value": "dateTimeAsIsoNoDateIfToday"}]}],
          description="All 56 leaf-level grocery/food products CBS tracks in the CPI "
                      "basket — one level more granular than the 12 top-level COICOP "
                      "categories on NL: Cost of Living."),

    barchart("Biggest year-on-year price movers", 0, 16, 24, 13, TOP_MOVERS,
             unit="percent", decimals=1, color=CAT[3], horizontal=True),

    table("Every product, year-on-year change", 0, 29, 24, 16, YOY_LATEST,
          decimals=1, sort=("YoY %", True)),

    timeseries("Selected product: index over time (2015=100)", 0, 45, 24, 10, PRODUCT_TREND,
               decimals=1, colors={"value": CAT[0]}, fill=15,
               description="Pick a product from the ${product} dropdown above."),
]

write(dashboard("nl-grocery-prices", "NL: Grocery Prices", panels, ["netherlands"],
                refresh="1h", time_from="2000-01-01T00:00:00Z", templating=[PRODUCT_VAR],
                description="Dutch consumer prices for 56 individual grocery/food "
                            "products — rice, bread, beef, milk, cheese, coffee and "
                            "more — CBS's most granular CPI breakdown, since 2000."),
      "NL/nl-grocery-prices")

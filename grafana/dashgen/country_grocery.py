"""One dashboard generator, five countries — Germany, Italy, Spain, Greece and France
(not Turkey, which has no product-level HICP data at all — see eurostat_grocery.py).

Unlike NL's grocery dashboard, eurostat_grocery.py only stores the index value, not a
separately-fetched YoY rate (fetching YoY per product would double an already-expensive
61-products x 5-countries pull) — so YoY here is computed in SQL via a year-ago join
instead of a stored ``_yoy`` indicator.
"""

import _lib
from _lib import CAT, dashboard, barchart, table, timeseries, write
from _eurostat_common import PRODUCT_LABELS

COUNTRIES = [
    ("DE", "DEU", "Germany"),
    ("IT", "ITA", "Italy"),
    ("ES", "ESP", "Spain"),
    ("GR", "GRC", "Greece"),
    ("FR", "FRA", "France"),
]

PRODUCT_KEYS = list(PRODUCT_LABELS)
RANGE_START = "2000-01-01"


def _label_case(column: str) -> str:
    whens = " ".join(
        f"WHEN 'cpi_product_{k}' THEN '{label}'" for k, label in PRODUCT_LABELS.items()
    )
    return f"CASE {column} {whens} ELSE {column} END"


for code, iso3, name in COUNTRIES:
    _lib._id = 0

    product_inlist = ",".join(f"'cpi_product_{k}'" for k in PRODUCT_KEYS)

    all_latest = f"""
    SELECT DISTINCT ON (indicator) {_label_case("indicator")} AS "Product",
           value AS "Index (2015=100)", period_date AS "Month"
    FROM price_index
    WHERE country_iso3='{iso3}' AND source='eurostat' AND indicator IN ({product_inlist})
    ORDER BY indicator, period_date DESC
    """

    yoy = f"""
    WITH latest AS (
      SELECT DISTINCT ON (indicator) indicator, value, period_date
      FROM price_index
      WHERE country_iso3='{iso3}' AND source='eurostat' AND indicator IN ({product_inlist})
      ORDER BY indicator, period_date DESC
    ),
    year_ago AS (
      SELECT l.indicator, p.value AS value_year_ago
      FROM latest l
      JOIN price_index p
        ON p.country_iso3='{iso3}' AND p.source='eurostat' AND p.indicator = l.indicator
       AND p.period_date = (l.period_date - interval '1 year')
    )
    SELECT {_label_case("latest.indicator")} AS "Product",
           round((100 * (latest.value - year_ago.value_year_ago)
                  / NULLIF(year_ago.value_year_ago, 0))::numeric, 2) AS "YoY %",
           latest.period_date AS "Month"
    FROM latest JOIN year_ago ON year_ago.indicator = latest.indicator
    ORDER BY 2 DESC
    """

    product_var = {
        "name": "product", "label": "Product", "type": "custom",
        "query": ",".join(f"{label} : {slug}" for slug, label in PRODUCT_LABELS.items()),
        "current": {"text": "Bread", "value": "bread"},
        "options": [
            {"text": label, "value": slug, "selected": slug == "bread"}
            for slug, label in PRODUCT_LABELS.items()
        ],
        "multi": False, "includeAll": False, "hide": 0,
    }

    product_trend = f"""
    SELECT period_date AS time, value FROM price_index
    WHERE country_iso3='{iso3}' AND source='eurostat' AND indicator='cpi_product_${{product}}'
      AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date)
    ORDER BY 1
    """

    panels = [
        table("Every tracked product, latest index value", 0, 0, 24, 16, all_latest,
              decimals=1, sort=("Index (2015=100)", True),
              overrides=[{"matcher": {"id": "byName", "options": "Month"},
                          "properties": [{"id": "unit",
                                          "value": "dateTimeAsIsoNoDateIfToday"}]}],
              description="61 leaf-level grocery/food products Eurostat tracks in the "
                          "HICP basket — one level more granular than the categories "
                          f"on {name}: Economy & Population."),

        barchart("Biggest year-on-year price movers", 0, 16, 24, 13, yoy,
                 unit="percent", decimals=1, color=CAT[3], horizontal=True),

        table("Every product, year-on-year change", 0, 29, 24, 16, yoy,
              decimals=1, sort=("YoY %", True)),

        timeseries("Selected product: index over time (2015=100)", 0, 45, 24, 10,
                   product_trend, decimals=1, colors={"value": CAT[0]}, fill=15,
                   description="Pick a product from the ${product} dropdown above."),
    ]

    write(dashboard(f"{code.lower()}-grocery-prices", f"{name}: Grocery Prices", panels,
                    [name.lower()], refresh="1h", time_from="2000-01-01T00:00:00Z",
                    templating=[product_var],
                    description=f"{name} consumer prices for 61 individual grocery/food "
                                f"products — rice, bread, beef, milk, cheese, coffee and "
                                f"more — Eurostat's most granular CPI breakdown, since "
                                f"2000 where the data goes back that far."),
          f"{code}/{code.lower()}-grocery-prices")

"""Shared query builders and constants for the NL/* dashboards.

Not a dashboard script itself — generate_all.py skips any file starting with "_".
"""

RANGE_START = "2000-01-01"
NL_CITIES = ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"]
CITY_LIST_SQL = ",".join(f"'{c}'" for c in NL_CITIES)

CITY_COLORS = {
    "Amsterdam": "#3987e5", "Rotterdam": "#d95926", "The Hague": "#199e70",
    "Utrecht": "#c98500", "Eindhoven": "#d55181",
}

# CPI category slug -> display label, mirrors nl_metrics.CPI_CATEGORIES on the collector
# side (kept as a plain literal here so the dashboard generator has no import dependency
# on the collector package).
CPI_CATEGORY_LABELS = {
    "food_and_drink": "Food & non-alc. drink",
    "alcohol_and_tobacco": "Alcohol & tobacco",
    "clothing_and_footwear": "Clothing & footwear",
    "housing_water_energy": "Housing, water & energy",
    "furnishings_household": "Furnishings & household",
    "health": "Health",
    "transport": "Transport",
    "communication": "Communication",
    "recreation_and_culture": "Recreation & culture",
    "education": "Education",
    "restaurants_and_hotels": "Restaurants & hotels",
    "misc_goods_and_services": "Misc. goods & services",
}


def nl(indicator: str, source: str | None = None) -> str:
    """A single-column ``time, value`` series for one price_index indicator, NLD only."""
    src = f"AND source='{source}' " if source else ""
    return (
        f"SELECT period_date AS time, value FROM price_index "
        f"WHERE country_iso3='NLD' AND indicator='{indicator}' {src}"
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


def nl_latest(indicator: str, source: str | None = None) -> str:
    src = f"AND source='{source}' " if source else ""
    return (
        f"SELECT value FROM price_index WHERE country_iso3='NLD' AND indicator='{indicator}' "
        f"{src}ORDER BY period_date DESC LIMIT 1"
    )


def nl_multi(indicators: list[str], source: str | None = None) -> str:
    """Long-format ``time, metric, value`` for several indicators in one panel."""
    src = f"AND source='{source}' " if source else ""
    inlist = ",".join(f"'{i}'" for i in indicators)
    return (
        f"SELECT period_date AS time, indicator AS metric, value FROM price_index "
        f"WHERE country_iso3='NLD' AND indicator IN ({inlist}) {src}"
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )

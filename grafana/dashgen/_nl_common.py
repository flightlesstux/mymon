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

# Leaf-level grocery/food product slug -> display label, mirrors
# nl_metrics.CPI_PRODUCTS on the collector side (same plain-literal-mirror pattern as
# CPI_CATEGORY_LABELS above, for the same reason — no import dependency on the collector).
CPI_PRODUCT_LABELS = {
    "rice": "Rice", "flour_and_other_grains": "Flour & other grains", "bread": "Bread",
    "other_bakery_products": "Other bakery products", "pizza_and_quiche": "Pizza & quiche",
    "pasta_and_couscous": "Pasta & couscous", "breakfast_cereals": "Breakfast cereals",
    "other_grain_products": "Other grain products", "beef_and_veal": "Beef & veal",
    "pork": "Pork", "lamb_and_goat": "Lamb & goat", "poultry": "Poultry",
    "other_meat": "Other meat", "smoked_dried_salted_meat": "Smoked/dried/salted meat",
    "other_meat_preparations": "Other meat preparations",
    "fresh_or_chilled_fish": "Fresh/chilled fish", "frozen_fish": "Frozen fish",
    "fresh_shellfish": "Fresh shellfish",
    "smoked_dried_salted_fish": "Smoked/dried/salted fish",
    "fish_preparations_and_preserves": "Fish preparations & preserves",
    "fresh_whole_milk": "Fresh whole milk",
    "fresh_semi_skimmed_milk": "Fresh semi-skimmed milk", "uht_milk": "UHT milk",
    "yoghurt": "Yoghurt", "cheese_and_quark": "Cheese & quark",
    "other_dairy_products": "Other dairy products", "eggs": "Eggs", "butter": "Butter",
    "margarine_and_vegetable_fats": "Margarine & vegetable fats", "olive_oil": "Olive oil",
    "other_edible_oils": "Other edible oils", "fresh_fruit": "Fresh fruit",
    "dried_fruit_and_nuts": "Dried fruit & nuts", "fruit_preserves": "Fruit preserves",
    "fresh_vegetables": "Fresh vegetables", "frozen_vegetables": "Frozen vegetables",
    "dried_vegetables": "Dried vegetables", "potatoes": "Potatoes", "crisps": "Crisps",
    "sugar": "Sugar", "jam_and_honey": "Jam & honey", "chocolate": "Chocolate",
    "sweets": "Sweets", "ice_cream": "Ice cream",
    "artificial_sweeteners": "Artificial sweeteners",
    "sauces_and_dressings": "Sauces & dressings",
    "salt_spices_and_herbs": "Salt, spices & herbs", "baby_food": "Baby food",
    "ready_meals": "Ready meals", "other_food_nec": "Other food", "coffee": "Coffee",
    "tea": "Tea", "cocoa_powder": "Cocoa powder", "mineral_water": "Mineral water",
    "soft_drinks": "Soft drinks",
    "fruit_and_vegetable_juices": "Fruit & vegetable juices",
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


# Mirrors nl_metrics.BIRTH_AGE_BRACKETS slugs on the collector side. CBS's own bracket
# boundaries (<20, 20-25, ..., 45+) are coarser at the tails than the 5-year-everywhere
# scheme Eurostat uses for the other six countries, so this is its own dict rather than
# a copy of _eurostat_common.AGE_BRACKET_LABELS.
BIRTH_AGE_BRACKET_LABELS = {
    "under_20": "<20", "20_25": "20-25", "25_30": "25-30", "30_35": "30-35",
    "35_40": "35-40", "40_45": "40-45", "45_plus": "45+",
}


def nl_multi(indicators: list[str], source: str | None = None) -> str:
    """Long-format ``time, metric, value`` for several indicators in one panel."""
    src = f"AND source='{source}' " if source else ""
    inlist = ",".join(f"'{i}'" for i in indicators)
    return (
        f"SELECT period_date AS time, indicator AS metric, value FROM price_index "
        f"WHERE country_iso3='NLD' AND indicator IN ({inlist}) {src}"
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )

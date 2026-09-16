"""Germany, Italy, Spain, Greece, Turkey and France: 61 individual grocery/food products
via Eurostat's HICP COICOP breakdown (``prc_hicp_midx``) — the same dataset
eurostat_metrics.py already uses for headline/food CPI, just at its most granular level
(one below the "food_and_drink" group total), and all six countries in one call per
product. Mirrors NL's nl_metrics.py grocery detail (56 CBS products); Eurostat's COICOP
list here is slightly richer (61 leaf codes) and doesn't exactly line up product-for-
product with CBS's — this is its own set, not a re-mapping onto NL's slugs.

Turkey has no data at all at this product level (confirmed live: a TR-only query for
any single product returns zero values, even though TR does have headline/category-level
HICP data via eurostat_metrics.py) — shown as "No data" honestly, not backfilled.

Shares the JSON-stat decoder and country-code mapping with eurostat_metrics.py.
"""

from __future__ import annotations

import logging
from typing import Any

from ..source import Ctx, Rows, Source
from .eurostat_metrics import GEO_TO_ISO3, GEOS, _decode, _period_from_time_code

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
SINCE = "2000-01"

# COICOP leaf code -> our indicator slug. Confirmed live against the full 468-entry
# coicop dimension list (2026-09).
PRODUCTS: dict[str, str] = {
    "CP01111": "rice", "CP01112": "flours_and_other_cereals", "CP01113": "bread",
    "CP01114": "other_bakery_products", "CP01115": "pizza_and_quiche",
    "CP01116": "pasta_products_and_couscous", "CP01117": "breakfast_cereals",
    "CP01118": "other_cereal_products", "CP01121": "beef_and_veal", "CP01122": "pork",
    "CP01123": "lamb_and_goat", "CP01124": "poultry", "CP01125": "other_meats",
    "CP01126": "edible_offal", "CP01127": "dried_salted_or_smoked_meat",
    "CP01128": "other_meat_preparations", "CP01131": "fresh_or_chilled_fish",
    "CP01132": "frozen_fish", "CP01133": "fresh_or_chilled_seafood",
    "CP01134": "frozen_seafood", "CP01135": "dried_smoked_or_salted_fish_and_seafood",
    "CP01136": "other_preserved_or_processed_fish_and_seafood",
    "CP01141": "fresh_whole_milk", "CP01142": "fresh_low_fat_milk",
    "CP01143": "preserved_milk", "CP01144": "yoghurt", "CP01145": "cheese_and_curd",
    "CP01146": "other_milk_products", "CP01147": "eggs", "CP01151": "butter",
    "CP01152": "margarine_and_other_vegetable_fats", "CP01153": "olive_oil",
    "CP01154": "other_edible_oils", "CP01155": "other_edible_animal_fats",
    "CP01161": "fresh_or_chilled_fruit", "CP01162": "frozen_fruit",
    "CP01163": "dried_fruit_and_nuts", "CP01164": "preserved_fruit_and_fruit_based_products",
    "CP01171": "fresh_or_chilled_vegetables", "CP01172": "frozen_vegetables",
    "CP01173": "dried_or_preserved_vegetables", "CP01174": "potatoes", "CP01175": "crisps",
    "CP01176": "other_tubers_and_products", "CP01181": "sugar",
    "CP01182": "jams_marmalades_and_honey", "CP01183": "chocolate",
    "CP01184": "confectionery_products", "CP01185": "edible_ices_and_ice_cream",
    "CP01186": "artificial_sugar_substitutes", "CP01191": "sauces_condiments",
    "CP01192": "salt_spices_and_culinary_herbs", "CP01193": "baby_food",
    "CP01194": "ready_made_meals", "CP01199": "other_food_products", "CP01211": "coffee",
    "CP01212": "tea", "CP01213": "cocoa_and_powdered_chocolate",
    "CP01221": "mineral_or_spring_waters", "CP01222": "soft_drinks",
    "CP01223": "fruit_and_vegetable_juices",
}


def _row(period, country_iso3: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _product_rows(ctx: Ctx, coicop: str, slug: str) -> list[dict[str, Any]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, "coicop": coicop, "unit": "I15",
              "sinceTimePeriod": SINCE}
    resp = ctx.http.get(f"{BASE}/prc_hicp_midx", params=query)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = []
    for dims, value in _decode(resp.json()):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, f"cpi_product_{slug}", value, "2015=100"))
    return rows


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, str], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for coicop, slug in upstreams:
        try:
            part = _product_rows(ctx, coicop, slug)
        except Exception as exc:  # noqa: BLE001 - one product must not sink the others
            log.warning("eurostat_grocery: %s failed: %s", slug, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_grocery: %s returned no rows", slug)
            failures += 1
            continue
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, tuple(PRODUCTS.items()))
    if not rows:
        raise RuntimeError("eurostat_grocery: every upstream failed")
    log.info("eurostat_grocery: %d rows (%d/%d upstream failures)",
              len(rows), failures, len(PRODUCTS))
    return [(TABLE, rows)]


SOURCE = Source(
    name="eurostat_grocery",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece, Turkey, France: 61 individual grocery/food "
        "products (rice, bread, beef, milk, cheese, coffee and more), Eurostat's most "
        "granular CPI breakdown, monthly since 2000 where the data goes back that far."
    ),
)

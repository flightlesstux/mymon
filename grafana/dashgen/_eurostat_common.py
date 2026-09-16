"""Shared display labels for country_grocery.py, mirrors nl_metrics/eurostat_grocery's
PRODUCTS slugs on the collector side (same plain-literal-mirror pattern as
_nl_common.CPI_PRODUCT_LABELS — no import dependency on the collector package).

Not a dashboard script itself — generate_all.py skips any file starting with "_".
"""

PRODUCT_LABELS = {
    "rice": "Rice", "flours_and_other_cereals": "Flours & other cereals", "bread": "Bread",
    "other_bakery_products": "Other bakery products", "pizza_and_quiche": "Pizza & quiche",
    "pasta_products_and_couscous": "Pasta & couscous", "breakfast_cereals": "Breakfast cereals",
    "other_cereal_products": "Other cereal products", "beef_and_veal": "Beef & veal",
    "pork": "Pork", "lamb_and_goat": "Lamb & goat", "poultry": "Poultry",
    "other_meats": "Other meats", "edible_offal": "Edible offal",
    "dried_salted_or_smoked_meat": "Dried/salted/smoked meat",
    "other_meat_preparations": "Other meat preparations",
    "fresh_or_chilled_fish": "Fresh/chilled fish", "frozen_fish": "Frozen fish",
    "fresh_or_chilled_seafood": "Fresh/chilled seafood", "frozen_seafood": "Frozen seafood",
    "dried_smoked_or_salted_fish_and_seafood": "Dried/smoked/salted fish & seafood",
    "other_preserved_or_processed_fish_and_seafood": "Other preserved fish & seafood",
    "fresh_whole_milk": "Fresh whole milk", "fresh_low_fat_milk": "Fresh low-fat milk",
    "preserved_milk": "Preserved milk", "yoghurt": "Yoghurt",
    "cheese_and_curd": "Cheese & curd", "other_milk_products": "Other milk products",
    "eggs": "Eggs", "butter": "Butter",
    "margarine_and_other_vegetable_fats": "Margarine & vegetable fats",
    "olive_oil": "Olive oil", "other_edible_oils": "Other edible oils",
    "other_edible_animal_fats": "Other edible animal fats",
    "fresh_or_chilled_fruit": "Fresh/chilled fruit", "frozen_fruit": "Frozen fruit",
    "dried_fruit_and_nuts": "Dried fruit & nuts",
    "preserved_fruit_and_fruit_based_products": "Preserved fruit products",
    "fresh_or_chilled_vegetables": "Fresh/chilled vegetables",
    "frozen_vegetables": "Frozen vegetables",
    "dried_or_preserved_vegetables": "Dried/preserved vegetables", "potatoes": "Potatoes",
    "crisps": "Crisps", "other_tubers_and_products": "Other tubers & products",
    "sugar": "Sugar", "jams_marmalades_and_honey": "Jams, marmalade & honey",
    "chocolate": "Chocolate", "confectionery_products": "Confectionery",
    "edible_ices_and_ice_cream": "Ice cream",
    "artificial_sugar_substitutes": "Artificial sweeteners",
    "sauces_condiments": "Sauces & condiments",
    "salt_spices_and_culinary_herbs": "Salt, spices & herbs", "baby_food": "Baby food",
    "ready_made_meals": "Ready meals", "other_food_products": "Other food products",
    "coffee": "Coffee", "tea": "Tea",
    "cocoa_and_powdered_chocolate": "Cocoa powder",
    "mineral_or_spring_waters": "Mineral water", "soft_drinks": "Soft drinks",
    "fruit_and_vegetable_juices": "Fruit & vegetable juices",
}

# Mirrors eurostat_cost_of_living.CATEGORIES slugs on the collector side.
COST_OF_LIVING_LABELS = {
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

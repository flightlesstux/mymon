"""One dashboard generator, six countries — construction, tourism, vehicle fleet and
(where Eurostat has it — not Turkey) agriculture, all from the eurostat_construction/
eurostat_tourism/eurostat_vehicles/eurostat_agriculture sources. Combined into one
"Sectors" dashboard per country rather than four separate ones, since each theme here
is only 1-2 indicators deep (unlike NL's richer per-theme CBS dashboards).
"""

import _lib
from _lib import CAT, dashboard, stat, timeseries, write

COUNTRIES = [
    ("DE", "DEU", "Germany", True),
    ("IT", "ITA", "Italy", True),
    ("ES", "ESP", "Spain", True),
    ("GR", "GRC", "Greece", True),
    ("TR", "TUR", "Turkey", False),  # no eurostat_agriculture data for Turkey
    ("FR", "FRA", "France", True),
]

RANGE_START = "2000-01-01"

FUEL_SLUGS = ["petrol", "diesel", "electric", "lpg", "cng"]
FUEL_COLORS = {f"vehicle_fleet_{slug}": CAT[i] for i, slug in enumerate(FUEL_SLUGS)}
LIVESTOCK_SLUGS = ["cattle_count", "pig_count", "sheep_count", "goat_count", "poultry_count"]
LIVESTOCK_COLORS = {slug: CAT[i] for i, slug in enumerate(LIVESTOCK_SLUGS)}


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


def q_multi(country_iso3: str, indicators: list[str]) -> str:
    inlist = ",".join(f"'{i}'" for i in indicators)
    return (
        f"SELECT period_date AS time, indicator AS metric, value FROM price_index "
        f"WHERE country_iso3='{country_iso3}' AND indicator IN ({inlist}) AND source='eurostat' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


for code, iso3, name, has_agriculture in COUNTRIES:
    _lib._id = 0

    fleet = q_multi(iso3, [f"vehicle_fleet_{s}" for s in FUEL_SLUGS])

    panels = [
        stat("Construction production index", 0, 0, 6, 4,
             q_latest(iso3, "construction_production_index"), decimals=1, color=CAT[0]),
        stat("Tourism nights spent, latest month", 6, 0, 6, 4,
             q_latest(iso3, "tourism_nights_spent"), unit="short", decimals=0, color=CAT[2]),
        stat("Electric cars in fleet", 12, 0, 6, 4,
             q_latest(iso3, "vehicle_fleet_electric"), unit="short", decimals=0, color=CAT[6]),
        stat("Petrol cars in fleet", 18, 0, 6, 4,
             q_latest(iso3, "vehicle_fleet_petrol"), unit="short", decimals=0, color=CAT[0]),

        timeseries("Construction sector production index (2021=100)", 0, 4, 24, 9,
                   q(iso3, "construction_production_index"), decimals=1,
                   colors={"value": CAT[0]}, fill=15,
                   description="Eurostat sts_copr_m, seasonally adjusted, monthly."),

        timeseries("Tourism: nights spent at accommodation", 0, 13, 24, 9,
                   q(iso3, "tourism_nights_spent"), unit="short", decimals=0,
                   colors={"value": CAT[2]}, fill=15, description="Monthly."),

        timeseries("Passenger car fleet by fuel type", 0, 22, 24, 10, fleet, unit="short",
                   decimals=0, colors=FUEL_COLORS, fill=0, legend="right",
                   description="Stock as of year end, not new sales — Eurostat doesn't "
                               "publish a fuel-type breakdown of new registrations "
                               "either. Coverage starts around the early 2010s and "
                               "varies by country and fuel type."),

        stat("Port cargo, latest year", 0, 32, 8, 4, q_latest(iso3, "port_cargo_1000t"),
             unit="short", decimals=0, color=CAT[4]),
        timeseries("National port cargo tonnage", 0, 36, 24, 9, q(iso3, "port_cargo_1000t"),
                   unit="short", decimals=0, colors={"value": CAT[4]}, fill=15,
                   description="Eurostat mar_mg_aa_cwh, annual, whole country — not "
                               "per-port like NL's Ports & Shipping dashboard."),
    ]

    if has_agriculture:
        livestock = q_multi(iso3, LIVESTOCK_SLUGS)
        panels += [
            stat("Cattle", 0, 45, 6, 4, q_latest(iso3, "cattle_count"), unit="short",
                 decimals=0, color=CAT[1]),
            stat("Pigs", 6, 45, 6, 4, q_latest(iso3, "pig_count"), unit="short",
                 decimals=0, color=CAT[3]),
            stat("Farm holdings with livestock", 12, 45, 12, 4,
                 q_latest(iso3, "farm_holdings_with_livestock"), unit="short", decimals=0,
                 color=CAT[4]),
            timeseries("Livestock", 0, 49, 24, 10, livestock, unit="short", decimals=0,
                       colors=LIVESTOCK_COLORS, fill=0, legend="right", points=True,
                       description="Eurostat farm structure survey, every ~3 years "
                                   "(2005-2023) — not annual, a real characteristic of "
                                   "this upstream data."),
        ]

    write(dashboard(f"{code.lower()}-sectors", f"{name}: Sectors", panels, [name.lower()],
                    refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name}: construction production, tourism, vehicle "
                                f"fleet by fuel type"
                                + (", and livestock/farm holdings" if has_agriculture else "")
                                + " — via Eurostat, since 2000 where the data goes back that far."),
          f"{code}/{code.lower()}-sectors")

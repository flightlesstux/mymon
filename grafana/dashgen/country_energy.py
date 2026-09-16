"""One dashboard generator, six countries — household energy tariffs and electricity
production mix from eurostat_energy.py.
"""

import _lib
from _lib import CAT, dashboard, stat, timeseries, write

COUNTRIES = [
    ("DE", "DEU", "Germany"),
    ("IT", "ITA", "Italy"),
    ("ES", "ESP", "Spain"),
    ("GR", "GRC", "Greece"),
    ("TR", "TUR", "Turkey"),
    ("FR", "FRA", "France"),
]

RANGE_START = "2000-01-01"

PRODUCTION_SLUGS = ["combustible_fuels", "hydro", "wind", "solar", "nuclear"]
PRODUCTION_COLORS = {
    f"electricity_production_gwh_{slug}": CAT[i] for i, slug in enumerate(PRODUCTION_SLUGS)
}


def q(iso3: str, indicator: str) -> str:
    return (
        f"SELECT period_date AS time, value FROM price_index "
        f"WHERE country_iso3='{iso3}' AND indicator='{indicator}' AND source='eurostat' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


def q_latest(iso3: str, indicator: str) -> str:
    return (
        f"SELECT value FROM price_index WHERE country_iso3='{iso3}' "
        f"AND indicator='{indicator}' AND source='eurostat' ORDER BY period_date DESC LIMIT 1"
    )


def q_multi(iso3: str, indicators: list[str]) -> str:
    inlist = ",".join(f"'{i}'" for i in indicators)
    return (
        f"SELECT period_date AS time, indicator AS metric, value FROM price_index "
        f"WHERE country_iso3='{iso3}' AND indicator IN ({inlist}) AND source='eurostat' "
        f"AND period_date >= '{RANGE_START}' AND $__timeFilter(period_date) ORDER BY 1"
    )


for code, iso3, name in COUNTRIES:
    _lib._id = 0

    production = q_multi(iso3, [f"electricity_production_gwh_{s}" for s in PRODUCTION_SLUGS])

    panels = [
        stat("Household gas price", 0, 0, 6, 4, q_latest(iso3, "gas_price_eur_per_kwh"),
             decimals=4, color=CAT[3], description="EUR/kWh, all taxes included."),
        stat("Household electricity price", 6, 0, 6, 4,
             q_latest(iso3, "electricity_price_eur_per_kwh"), decimals=4, color=CAT[1],
             description="EUR/kWh, all taxes included."),
        stat("Wind generation, latest year", 12, 0, 6, 4,
             q_latest(iso3, "electricity_production_gwh_wind"), unit="short", decimals=0,
             color=CAT[0]),
        stat("Solar generation, latest year", 18, 0, 6, 4,
             q_latest(iso3, "electricity_production_gwh_solar"), unit="short", decimals=0,
             color=CAT[3]),

        timeseries("Household gas price (EUR/kWh, incl. taxes)", 0, 4, 12, 9,
                   q(iso3, "gas_price_eur_per_kwh"), decimals=4,
                   colors={"value": CAT[3]}, fill=15,
                   description="Eurostat nrg_pc_202, half-yearly, mid-size household band."),
        timeseries("Household electricity price (EUR/kWh, incl. taxes)", 12, 4, 12, 9,
                   q(iso3, "electricity_price_eur_per_kwh"), decimals=4,
                   colors={"value": CAT[1]}, fill=15,
                   description="Eurostat nrg_pc_204, half-yearly, all consumption bands."),

        timeseries("Electricity production by source", 0, 13, 24, 10, production, unit="short",
                   decimals=0, colors=PRODUCTION_COLORS, fill=0, legend="right",
                   description="Eurostat nrg_ind_peh, annual gross production, GWh."),
    ]

    write(dashboard(f"{code.lower()}-energy", f"{name}: Energy", panels, [name.lower()],
                    refresh="1h", time_from="2000-01-01T00:00:00Z",
                    description=f"{name}: household gas and electricity tariffs, and "
                                f"electricity production mix by source — via Eurostat, "
                                f"since 2000 where the data goes back that far."),
          f"{code}/{code.lower()}-energy")

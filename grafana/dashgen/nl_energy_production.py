from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl_latest, nl_multi

VOLUME = nl_multi([
    "electricity_production_gwh_solar", "electricity_production_gwh_wind",
    "electricity_production_gwh_natural_gas", "electricity_production_gwh_coal",
    "electricity_production_gwh_nuclear", "electricity_production_gwh_biomass",
], "cbs")
SHARE = nl_multi([
    "electricity_share_pct_renewable_total", "electricity_share_pct_nonrenewable_total",
], "cbs")
RENEWABLE_MIX = nl_multi([
    "electricity_share_pct_solar", "electricity_share_pct_wind",
    "electricity_share_pct_natural_gas", "electricity_share_pct_coal",
    "electricity_share_pct_nuclear", "electricity_share_pct_biomass",
], "cbs")

SOURCE_COLORS = {
    "electricity_production_gwh_solar": CAT[3], "electricity_share_pct_solar": CAT[3],
    "electricity_production_gwh_wind": CAT[0], "electricity_share_pct_wind": CAT[0],
    "electricity_production_gwh_natural_gas": CAT[7], "electricity_share_pct_natural_gas": CAT[7],
    "electricity_production_gwh_coal": CAT[1], "electricity_share_pct_coal": CAT[1],
    "electricity_production_gwh_nuclear": CAT[6], "electricity_share_pct_nuclear": CAT[6],
    "electricity_production_gwh_biomass": CAT[2], "electricity_share_pct_biomass": CAT[2],
    "electricity_share_pct_renewable_total": CAT[2],
    "electricity_share_pct_nonrenewable_total": CAT[5],
}

panels = [
    stat("Renewable share of production", 0, 0, 6, 4,
         nl_latest("electricity_share_pct_renewable_total", "cbs"),
         unit="percent", decimals=1, color=CAT[2]),
    stat("Solar, GWh/yr", 6, 0, 6, 4, nl_latest("electricity_production_gwh_solar", "cbs"),
         unit="short", decimals=0, color=CAT[3]),
    stat("Wind, GWh/yr", 12, 0, 6, 4, nl_latest("electricity_production_gwh_wind", "cbs"),
         unit="short", decimals=0, color=CAT[0]),
    stat("Natural gas, GWh/yr", 18, 0, 6, 4,
         nl_latest("electricity_production_gwh_natural_gas", "cbs"),
         unit="short", decimals=0, color=CAT[7]),

    timeseries("Electricity production by source (GWh/year)", 0, 4, 24, 10, VOLUME,
               unit="short", decimals=0, colors=SOURCE_COLORS, fill=0, legend="right",
               description="CBS 86266NED, gross annual electricity production by energy "
                           "carrier — one figure per year, so this fills in slowly."),

    timeseries("Renewable vs. non-renewable share of total generation", 0, 15, 12, 9, SHARE,
               unit="percent", decimals=1,
               colors={"electricity_share_pct_renewable_total": CAT[2],
                       "electricity_share_pct_nonrenewable_total": CAT[5]}, fill=15),
    timeseries("Renewable mix, share of total generation", 12, 15, 12, 9, RENEWABLE_MIX,
               unit="percent", decimals=1, colors=SOURCE_COLORS, fill=0, legend="right"),
]

write(dashboard("nl-energy-production", "NL: Energy Production", panels, ["netherlands"],
                refresh="1h", time_from="2000-01-01T00:00:00Z",
                description="Dutch gross electricity production by energy carrier, "
                            "annual (CBS 86266NED), since 2000 where the data goes back "
                            "that far."),
      "NL/nl-energy-production")

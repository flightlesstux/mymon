from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import nl, nl_latest, nl_multi

AGE_BREAKDOWN = nl_multi([
    "unemployment_rate_pct_15_24", "unemployment_rate_pct_25_44", "unemployment_rate_pct_45_74",
], "cbs")
GENDER_BREAKDOWN = nl_multi(["unemployment_rate_pct_men", "unemployment_rate_pct_women"], "cbs")
NATURAL_CHANGE = nl_multi(["births", "deaths"], "cbs")
MIGRATION = nl_multi(["immigration", "emigration"], "cbs")

panels = [
    stat("Population", 0, 0, 6, 4, nl_latest("population_total", "cbs"),
         unit="short", decimals=0, color=CAT[0]),
    stat("Population growth, latest month", 6, 0, 6, 4, nl_latest("population_growth", "cbs"),
         unit="short", decimals=0, color=CAT[2]),
    stat("Labour participation", 12, 0, 6, 4, nl_latest("labour_participation_pct", "cbs"),
         unit="percent", decimals=1, color=CAT[6]),
    stat("Unemployment, 15-24", 18, 0, 6, 4, nl_latest("unemployment_rate_pct_15_24", "cbs"),
         unit="percent", decimals=1, color=CAT[3]),

    timeseries("Population", 0, 4, 24, 9, nl("population_total", "cbs"),
               unit="short", decimals=0, colors={"value": CAT[0]}, fill=15),

    timeseries("Births vs. deaths, per month", 0, 13, 12, 9, NATURAL_CHANGE, unit="short",
               decimals=0, colors={"births": CAT[2], "deaths": CAT[7]}, fill=0),
    timeseries("Immigration vs. emigration, per month", 12, 13, 12, 9, MIGRATION, unit="short",
               decimals=0, colors={"immigration": CAT[0], "emigration": CAT[3]}, fill=0),

    timeseries("Unemployment rate, seasonally adjusted", 0, 22, 12, 9,
               nl("unemployment_rate_pct", "cbs"), unit="percent", decimals=1,
               colors={"value": CAT[2]}, fill=15),
    timeseries("Labour participation rate", 12, 22, 12, 9, nl("labour_participation_pct", "cbs"),
               unit="percent", decimals=1, colors={"value": CAT[6]}, fill=15,
               description="Net labour participation, seasonally adjusted (CBS 80590ned)."),

    timeseries("Unemployment by age group", 0, 31, 12, 9, AGE_BREAKDOWN, unit="percent",
               decimals=1, colors={"unemployment_rate_pct_15_24": CAT[3],
                                    "unemployment_rate_pct_25_44": CAT[0],
                                    "unemployment_rate_pct_45_74": CAT[6]}, fill=0),
    timeseries("Unemployment by gender", 12, 31, 12, 9, GENDER_BREAKDOWN, unit="percent",
               decimals=1, colors={"unemployment_rate_pct_men": CAT[0],
                                    "unemployment_rate_pct_women": CAT[4]}, fill=0),
]

write(dashboard("nl-population-labour", "NL: Population & Labour Market", panels,
                ["netherlands"], refresh="1h", time_from="2000-01-01T00:00:00Z",
                description="Dutch population, births/deaths, migration, labour "
                            "participation and unemployment by age group and gender, "
                            "since 2000 where the data goes back that far."),
      "NL/nl-population-labour")

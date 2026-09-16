from _lib import CAT, dashboard, stat, timeseries, write
from _nl_common import BIRTH_AGE_BRACKET_LABELS

# This dashboard deliberately doesn't use _nl_common's nl()/nl_multi() helpers — those
# floor every query at RANGE_START (2000-01-01), but the annual CBS series here (births
# detail, life expectancy) go back to 1950, and the monthly counts (births/deaths/
# migration) go back to 1995. Raw SQL with only $__timeFilter lets the full history show.

MONTHLY_BIRTHS_DEATHS = """
SELECT period_date AS time, indicator AS metric, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ('births','deaths')
  AND $__timeFilter(period_date) ORDER BY 1
"""

MONTHLY_MIGRATION = """
SELECT period_date AS time, indicator AS metric, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ('immigration','emigration')
  AND $__timeFilter(period_date) ORDER BY 1
"""

NET_MIGRATION = """
SELECT im.period_date AS time, im.value - em.value AS value
FROM price_index im JOIN price_index em
  ON em.period_date = im.period_date AND em.country_iso3 = im.country_iso3 AND em.source = im.source
WHERE im.country_iso3='NLD' AND im.source='cbs' AND im.indicator='immigration' AND em.indicator='emigration'
  AND $__timeFilter(im.period_date)
ORDER BY 1
"""

FERTILITY = """
SELECT period_date AS time, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator='fertility_rate_children_per_woman'
  AND $__timeFilter(period_date) ORDER BY 1
"""

LIFE_EXPECTANCY = """
SELECT period_date AS time, indicator AS metric, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs'
  AND indicator IN ('life_expectancy_years_men','life_expectancy_years_women')
  AND $__timeFilter(period_date) ORDER BY 1
"""

MOTHER_AGE = """
SELECT period_date AS time, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator='avg_mother_age_years'
  AND $__timeFilter(period_date) ORDER BY 1
"""

STILLBIRTH = """
SELECT period_date AS time, value FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator='stillbirth_rate_per_1000'
  AND $__timeFilter(period_date) ORDER BY 1
"""

BIRTH_AGE_WHENS = " ".join(
    f"WHEN 'births_by_mother_age_{k}' THEN '{label}'" for k, label in BIRTH_AGE_BRACKET_LABELS.items()
)
BIRTH_AGE_INLIST = ",".join(f"'births_by_mother_age_{k}'" for k in BIRTH_AGE_BRACKET_LABELS)
BIRTHS_BY_MOTHER_AGE = f"""
SELECT period_date AS time, CASE indicator {BIRTH_AGE_WHENS} ELSE indicator END AS metric, value
FROM price_index
WHERE country_iso3='NLD' AND source='cbs' AND indicator IN ({BIRTH_AGE_INLIST})
  AND $__timeFilter(period_date) ORDER BY 1
"""
BIRTH_AGE_COLORS = {label: CAT[i % len(CAT)] for i, label in enumerate(BIRTH_AGE_BRACKET_LABELS.values())}


def _latest(indicator: str) -> str:
    return (
        f"SELECT value FROM price_index WHERE country_iso3='NLD' AND source='cbs' "
        f"AND indicator='{indicator}' ORDER BY period_date DESC LIMIT 1"
    )


panels = [
    stat("Births, latest month", 0, 0, 4, 4, _latest("births"), unit="short", decimals=0, color=CAT[2]),
    stat("Deaths, latest month", 4, 0, 4, 4, _latest("deaths"), unit="short", decimals=0, color=CAT[7]),
    stat("Immigration, latest month", 8, 0, 4, 4, _latest("immigration"), unit="short", decimals=0, color=CAT[0]),
    stat("Emigration, latest month", 12, 0, 4, 4, _latest("emigration"), unit="short", decimals=0, color=CAT[3]),
    stat("Fertility rate, children/woman", 16, 0, 4, 4, _latest("fertility_rate_children_per_woman"),
         decimals=2, color=CAT[4]),
    stat("Life expectancy at birth", 20, 0, 4, 4, _latest("life_expectancy_years_total"),
         unit="short", decimals=1, color=CAT[6]),

    timeseries("Births vs. deaths, per month", 0, 4, 12, 9, MONTHLY_BIRTHS_DEATHS, unit="short",
               decimals=0, colors={"births": CAT[2], "deaths": CAT[7]}, fill=0,
               description="CBS 83474NED, monthly, back to 1995."),
    timeseries("Immigration vs. emigration, per month", 12, 4, 12, 9, MONTHLY_MIGRATION, unit="short",
               decimals=0, colors={"immigration": CAT[0], "emigration": CAT[3]}, fill=0),

    timeseries("Net migration, per month (immigration − emigration)", 0, 13, 24, 9, NET_MIGRATION,
               unit="short", decimals=0, colors={"value": CAT[6]}, fill=15, points=True,
               description="Positive = more people moved to NL than left, that month."),

    timeseries("Total fertility rate (children per woman)", 0, 22, 12, 9, FERTILITY, decimals=3,
               colors={"value": CAT[4]}, fill=15,
               description="CBS 85722NED, annual, back to 1950. 2.1 is roughly the "
                           "replacement rate; the Netherlands has been below it since the 1970s."),
    timeseries("Life expectancy at birth, by gender", 12, 22, 12, 9, LIFE_EXPECTANCY, unit="short",
               decimals=1, colors={"life_expectancy_years_men": CAT[0],
                                    "life_expectancy_years_women": CAT[4]}, fill=0,
               description="CBS 37360ned, annual, back to 1950."),

    timeseries("Average age of mother at childbirth", 0, 31, 12, 9, MOTHER_AGE, unit="short",
               decimals=1, colors={"value": CAT[1]}, fill=15,
               description="CBS 85722NED, annual, back to 1950."),
    timeseries("Stillbirth rate (per 1,000 births, 28+ weeks)", 12, 31, 12, 9, STILLBIRTH,
               decimals=1, colors={"value": CAT[7]}, fill=40, lw=1),

    timeseries("Live births by mother's age bracket", 0, 40, 24, 10, BIRTHS_BY_MOTHER_AGE,
               unit="short", decimals=0, colors=BIRTH_AGE_COLORS, fill=0, legend="right",
               points=True,
               description="CBS 37744ned, annual since 1950. Own bracket boundaries "
                           "(<20, 20-25, ..., 45+), coarser at the tails than the "
                           "5-year-everywhere scheme used for the other six countries."),
]

write(dashboard("nl-births-deaths-migration", "NL: Births, Deaths & Migration", panels,
                ["netherlands"], refresh="1h", time_from="1950-01-01T00:00:00Z",
                description="Dutch births, deaths, immigration and emigration counts "
                            "(monthly since 1995), plus fertility rate, life expectancy "
                            "and birth detail (annual since 1950) — the deepest history "
                            "any NL dashboard here goes back to."),
      "NL/nl-births-deaths-migration")

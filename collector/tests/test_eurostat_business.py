from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_business as eb
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_bankruptcy_rows_maps_sectors_and_geo():
    data = jsonstat(
        ["nace_r2", "geo", "time"], [2, 2, 1],
        {"nace_r2": ["B-S_X_O_S94", "F"], "geo": ["DE", "FR"], "time": ["2026-08"]},
        {"0": 105.0, "1": 98.0, "2": 110.0, "3": 92.0},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_rb_m").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = eb._bankruptcy_rows(_ctx())
    by_key = {(r["country_iso3"], r["indicator"]): r["value"] for r in rows}
    assert by_key[("DEU", "bankruptcy_index_total")] == 105.0
    assert by_key[("FRA", "bankruptcy_index_total")] == 98.0
    assert by_key[("DEU", "bankruptcy_index_construction")] == 110.0
    assert by_key[("FRA", "bankruptcy_index_construction")] == 92.0
    assert all(r["period_date"] == date(2026, 8, 1) for r in rows)


def test_geo_to_iso3_excludes_the_four_countries_with_no_data():
    assert set(eb.GEO_TO_ISO3) == {"DE", "FR"}


def _ctx():
    return eb.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

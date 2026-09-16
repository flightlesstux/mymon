from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_tourism as et
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_nights_spent_rows():
    data = jsonstat(
        ["geo", "time"], [2, 1], {"geo": ["ES", "EL"], "time": ["2026-01"]},
        {"0": 25000000, "1": 8000000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/tour_occ_nim").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = et._nights_spent_rows(_ctx())
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["ESP"] == 25000000
    assert by_country["GRC"] == 8000000
    assert all(r["indicator"] == "tourism_nights_spent"
               and r["period_date"] == date(2026, 1, 1) for r in rows)


def _ctx():
    return et.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_construction as ec
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_construction_production_rows():
    data = jsonstat(
        ["geo", "time"], [2, 1], {"geo": ["DE", "TR"], "time": ["2026-01"]},
        {"0": 92.2, "1": 105.5},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_copr_m").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ec._construction_production_rows(_ctx())
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["DEU"] == 92.2
    assert by_country["TUR"] == 105.5
    assert all(r["indicator"] == "construction_production_index"
               and r["period_date"] == date(2026, 1, 1) for r in rows)


@respx.mock
def test_fetch_raises_when_no_data():
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_copr_m").mock(
        return_value=httpx.Response(200, json=jsonstat(["geo", "time"], [0, 0], {}, {}))
    )
    try:
        ec.fetch(_ctx())
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def _ctx():
    return ec.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

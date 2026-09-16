from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_ports as ep
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_port_cargo_rows_uses_rep_mar_dimension():
    data = jsonstat(
        ["rep_mar", "time"], [2, 1], {"rep_mar": ["DE", "TR"], "time": ["2024"]},
        {"0": 300000, "1": 450000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/mar_mg_aa_cwh").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = ep._port_cargo_rows(_ctx())
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["DEU"] == 300000
    assert by_country["TUR"] == 450000
    assert all(r["indicator"] == "port_cargo_1000t" and r["period_date"] == date(2024, 1, 1)
               for r in rows)


def _ctx():
    return ep.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_grocery as eg
from tests.test_eurostat_metrics import jsonstat


@respx.mock
def test_product_rows_maps_geo_to_iso3():
    data = jsonstat(
        ["geo", "time"], [2, 1], {"geo": ["DE", "IT"], "time": ["2026-01"]},
        {"0": 147.3, "1": 152.1},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = eg._product_rows(_ctx(), "CP01113", "bread")
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["DEU"] == 147.3
    assert by_country["ITA"] == 152.1
    assert all(r["indicator"] == "cpi_product_bread" and r["period_date"] == date(2026, 1, 1)
               for r in rows)


def test_products_covers_61_leaf_codes():
    assert len(eg.PRODUCTS) == 61
    assert eg.PRODUCTS["CP01113"] == "bread"
    assert eg.PRODUCTS["CP01211"] == "coffee"


@respx.mock
def test_fetch_survives_one_product_failing():
    ok = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2026-01"]}, {"0": 100.0})

    def responder(request):
        if "CP01111" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, json=ok)

    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        side_effect=responder
    )
    table, rows = eg.fetch(_ctx())[0]
    assert table == "price_index"
    assert not any(r["indicator"] == "cpi_product_rice" for r in rows)
    assert any(r["indicator"] == "cpi_product_bread" for r in rows)


def _ctx():
    return eg.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

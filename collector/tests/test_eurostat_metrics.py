from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import eurostat_metrics as em


def jsonstat(dim_ids, sizes, categories, values):
    """Build a minimal JSON-stat v1.1 payload. ``categories`` is {dim_id: [codes...]},
    ``values`` is {flat_index_str: number}."""
    dimension = {}
    for dim_id, codes in categories.items():
        dimension[dim_id] = {"category": {"index": {c: i for i, c in enumerate(codes)}}}
    return {"id": dim_ids, "size": sizes, "dimension": dimension, "value": values}


def test_decode_computes_flat_index_correctly():
    # geo has 2 codes, time has 3 codes -> size [1,2,3], strides [6,3,1] but only
    # meaningful dims matter; flat_index = geo_idx*3 + time_idx
    data = jsonstat(
        ["freq", "geo", "time"], [1, 2, 3],
        {"freq": ["M"], "geo": ["DE", "TR"], "time": ["2026-01", "2026-02", "2026-03"]},
        {"0": 1.1, "1": 1.2, "2": 1.3, "3": 2.1, "4": 2.2, "5": 2.3},
    )
    out = em._decode(data)
    by_key = {(d["geo"], d["time"]): v for d, v in out}
    assert by_key[("DE", "2026-01")] == 1.1
    assert by_key[("DE", "2026-03")] == 1.3
    assert by_key[("TR", "2026-01")] == 2.1
    assert by_key[("TR", "2026-03")] == 2.3


def test_decode_skips_null_values():
    data = jsonstat(
        ["geo", "time"], [2, 1], {"geo": ["DE", "TR"], "time": ["2026-01"]},
        {"0": 1.5},  # index 1 (TR) simply absent, as Eurostat does for unpublished data
    )
    out = em._decode(data)
    assert len(out) == 1
    assert out[0][0]["geo"] == "DE"


def test_period_from_time_code():
    assert em._period_from_time_code("2026") == date(2026, 1, 1)
    assert em._period_from_time_code("2026-Q3") == date(2026, 7, 1)
    assert em._period_from_time_code("2026-08") == date(2026, 8, 1)
    assert em._period_from_time_code("garbage") is None


@respx.mock
def test_cpi_index_rows_maps_geo_to_iso3():
    data = jsonstat(
        ["unit", "coicop", "geo", "time"], [1, 1, 5, 1],
        {"unit": ["I15"], "coicop": ["CP00"], "geo": em.GEOS, "time": ["2026-01"]},
        {"0": 126.4, "1": 130.0, "2": 110.0, "3": 105.0, "4": 200.0},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = em._cpi_index_rows(_ctx())
    by_country = {r["country_iso3"]: r["value"] for r in rows}
    assert by_country["DEU"] == 126.4
    assert by_country["TUR"] == 200.0
    assert all(r["period_date"] == date(2026, 1, 1) and r["indicator"] == "cpi_index"
               for r in rows)


@respx.mock
def test_a_failing_cpi_series_does_not_discard_a_successful_one():
    # regression: _cpi_index_rows and _cpi_inflation_rows must be independently
    # resilient upstreams, not one function making both calls internally — a 500 on
    # one must not discard the other's already-fetched rows
    ok = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2026-01"]}, {"0": 126.4})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        return_value=httpx.Response(200, json=ok)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr").mock(
        return_value=httpx.Response(500)
    )
    index_rows = em._cpi_index_rows(_ctx())
    assert len(index_rows) == 1
    assert index_rows[0]["value"] == 126.4


@respx.mock
def test_demographics_rows_maps_indicators():
    data = jsonstat(
        ["indic_de", "geo", "time"], [4, 1, 1],
        {"indic_de": ["LBIRTH", "DEATH", "CNMIGRAT", "GROW"], "geo": ["DE"], "time": ["2020"]},
        {"0": 800000, "1": 900000, "2": 50000, "3": -50000},
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_gind").mock(
        return_value=httpx.Response(200, json=data)
    )
    rows = em._demographics_rows(_ctx())
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["births"] == 800000
    assert by_indicator["deaths"] == 900000
    assert by_indicator["net_migration"] == 50000
    assert by_indicator["population_growth"] == -50000
    assert all(r["country_iso3"] == "DEU" for r in rows)


@respx.mock
def test_fetch_survives_one_upstream_failing():
    ok = jsonstat(["geo", "time"], [1, 1], {"geo": ["DE"], "time": ["2026-01"]}, {"0": 4.0})
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx").mock(
        return_value=httpx.Response(200, json=ok)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_gind").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bsco_m").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bsin_m_r2").mock(
        return_value=httpx.Response(500)
    )
    table, rows = em.fetch(_ctx())[0]
    assert table == "price_index"
    assert any(r["indicator"] == "cpi_index" for r in rows)


def _ctx():
    return em.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

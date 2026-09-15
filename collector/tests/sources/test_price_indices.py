from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from mymon_collector.sources import price_indices as pi
from tests.conftest import fixture_bytes, fixture_json, fixture_text

PK = {"period_date", "country_iso3", "indicator", "source"}
COLS = PK | {"value", "unit"}

WB_RE = r"https://api\.worldbank\.org/v2/country/all/indicator/(?P<ind>[A-Z.]+)\?.*"
FAO_CSV_RE = r"https://www\.fao\.org/media/docs/.*/food_price_indices_data\.csv.*"


def _wb_side_effect(request, ind):
    name = {"FP.CPI.TOTL.ZG": "cpi", "PA.NUS.PPP": "ppp", "NY.GDP.PCAP.CD": "gdp"}[ind]
    return httpx.Response(200, json=fixture_json(f"price_indices_worldbank_{name}.json"))


def _mock_all():
    respx.get(url__regex=WB_RE).mock(side_effect=_wb_side_effect)
    respx.get(pi.BIGMAC_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("price_indices_bigmac.csv"))
    )
    respx.get(pi.FAO_PAGE_URL).mock(
        return_value=httpx.Response(200, text=fixture_text("price_indices_fao_page.html"))
    )
    respx.get(url__regex=FAO_CSV_RE).mock(
        return_value=httpx.Response(200, content=fixture_bytes("price_indices_fao.csv"))
    )


def _by(rows, source, indicator=None):
    return [
        r
        for r in rows
        if r["source"] == source and (indicator is None or r["indicator"] == indicator)
    ]


def test_source_metadata():
    assert pi.SOURCE.name == "price_indices"
    assert pi.SOURCE.interval == 86400
    assert pi.SOURCE.tables == ["price_index"]
    assert pi.SOURCE.backfill is None
    assert pi.SOURCE.requires_env == []


@respx.mock
def test_fetch_all_upstreams(ctx):
    _mock_all()
    out = pi.fetch(ctx)
    assert [t for t, _ in out] == ["price_index"]
    rows = out[0][1]
    assert all(set(r) == COLS for r in rows)
    assert all(r[k] is not None for r in rows for k in PK)

    # World Bank: per fixture 9 records -> drop EUU aggregate, empty iso3, null value, bad year
    wb = _by(rows, "worldbank")
    assert {r["country_iso3"] for r in wb} == {"DEU", "TUR", "WLD", "EMU", "USA"}
    cpi = _by(rows, "worldbank", "cpi_inflation_pct")
    assert len(cpi) == 5
    tur = next(r for r in cpi if r["country_iso3"] == "TUR")
    assert tur["period_date"] == date(2024, 12, 31)
    assert tur["value"] == pytest.approx(58.5064507300342)
    assert tur["unit"] == "%"
    ppp = _by(rows, "worldbank", "ppp_factor")
    assert {r["country_iso3"] for r in ppp} == {"DEU", "TUR", "USA"}  # EMU/EUU/WLD are null
    assert next(r for r in ppp if r["country_iso3"] == "DEU")["value"] == pytest.approx(0.700862)
    assert ppp[0]["unit"] == "LCU per intl $"
    gdp = _by(rows, "worldbank", "gdp_per_capita_usd")
    assert len(gdp) == 5
    assert next(r for r in gdp if r["country_iso3"] == "WLD")["period_date"] == date(2023, 12, 31)
    assert gdp[0]["unit"] == "USD"

    # Big Mac: 5 good rows x 3 indicators + 1 row without USD_raw (2 indicators); bad row skipped
    bm = _by(rows, "economist")
    assert len(bm) == 5 * 3 + 2
    tur_usd = next(
        r for r in bm if r["country_iso3"] == "TUR" and r["indicator"] == "bigmac_usd"
    )
    assert tur_usd["period_date"] == date(2024, 7, 1)
    assert tur_usd["value"] == pytest.approx(4.68130859186238)
    assert tur_usd["unit"] == "USD"
    tur_local = next(
        r for r in bm if r["country_iso3"] == "TUR" and r["indicator"] == "bigmac_local"
    )
    assert tur_local["value"] == 155.0
    assert tur_local["unit"] == "TRY"
    tur_raw = next(
        r for r in bm if r["country_iso3"] == "TUR" and r["indicator"] == "bigmac_usd_raw_pct"
    )
    assert tur_raw["value"] == pytest.approx(-17.727)
    assert tur_raw["unit"] == "%"
    xxx = [r for r in bm if r["country_iso3"] == "XXX"]
    assert {r["indicator"] for r in xxx} == {"bigmac_usd", "bigmac_local"}

    # FAO: 5 data lines x 6 indicators, all WLD, first of month
    fao = _by(rows, "fao")
    assert len(fao) == 5 * 6
    assert {r["country_iso3"] for r in fao} == {"WLD"}
    assert {r["indicator"] for r in fao} == {
        "fao_food_index", "fao_meat", "fao_dairy", "fao_cereals", "fao_oils", "fao_sugar"
    }  # fmt: skip
    first = next(
        r
        for r in fao
        if r["period_date"] == date(1990, 1, 1) and r["indicator"] == "fao_food_index"
    )
    assert first["value"] == 64.4
    assert first["unit"] == "index 2014-16=100"
    oils = next(
        r for r in fao if r["period_date"] == date(2026, 8, 1) and r["indicator"] == "fao_oils"
    )
    assert oils["value"] == 196.9


@respx.mock
def test_one_upstream_failing_keeps_others(ctx):
    respx.get(url__regex=WB_RE).mock(return_value=httpx.Response(500))
    respx.get(pi.BIGMAC_URL).mock(
        return_value=httpx.Response(200, content=fixture_bytes("price_indices_bigmac.csv"))
    )
    respx.get(pi.FAO_PAGE_URL).mock(return_value=httpx.Response(503))
    rows = pi.fetch(ctx)[0][1]
    assert {r["source"] for r in rows} == {"economist"}


@respx.mock
def test_all_upstreams_failing_raises(ctx):
    respx.get(url__regex=WB_RE).mock(return_value=httpx.Response(500))
    respx.get(pi.BIGMAC_URL).mock(return_value=httpx.Response(404))
    respx.get(pi.FAO_PAGE_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError):
        pi.fetch(ctx)


def test_fao_link_prefers_csv_and_unescapes():
    url = pi._fao_csv_url(fixture_text("price_indices_fao_page.html"))
    assert url.endswith("food_price_indices_data.csv")


def test_fao_tolerant_dates_and_headers():
    text = (
        "FAO Food Price Index,,,\n"
        "Date,Food Price Index,Meat,Dairy,Cereals,Vegetable Oils,Sugar\n"
        "Jan-1991,100.5,1,2,3,4,5\n"
        "1991-02,101.0,,2,3,4,5\n"
        "garbage,1,2,3,4,5,6\n"
    )
    rows = pi._fao_rows(text)
    assert len(rows) == 6 + 5
    assert rows[0]["period_date"] == date(1991, 1, 1)
    assert {r["indicator"] for r in rows if r["period_date"] == date(1991, 2, 1)} == {
        "fao_food_index", "fao_dairy", "fao_cereals", "fao_oils", "fao_sugar"
    }  # fmt: skip


def test_worldbank_bad_payload_raises():
    with pytest.raises(ValueError):
        pi._worldbank_rows({"message": "nope"}, "cpi_inflation_pct", "%")

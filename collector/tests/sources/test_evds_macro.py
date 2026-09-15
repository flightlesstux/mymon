from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import evds_macro
from tests.conftest import fixture_json

EVDS_RE = r"https://evds3\.tcmb\.gov\.tr/igmevdsms-dis/series=.*"
COLS = {"period_date", "country_iso3", "indicator", "value", "unit", "source"}


@pytest.fixture
def keyed_ctx(ctx):
    ctx.cfg["env"]["EVDS_API_KEY"] = "test"
    return ctx


def test_source_metadata():
    assert evds_macro.SOURCE.name == "evds_macro"
    assert evds_macro.SOURCE.interval == 86400
    assert evds_macro.SOURCE.requires_env == ["EVDS_API_KEY"]
    assert evds_macro.SOURCE.tables == ["price_index"]
    assert evds_macro.SOURCE.backfill is None


def test_build_url_keeps_query_in_path():
    url = evds_macro.build_url(["TP.FG.J0", "TP.X"], "01-01-2010", "15-09-2026")
    assert url == (
        "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
        "series=TP.FG.J0-TP.X&startDate=01-01-2010&endDate=15-09-2026&type=json"
    )
    assert "?" not in url


@respx.mock
def test_fetch_parses_monthly_and_daily_periods(keyed_ctx):
    route = respx.get(url__regex=EVDS_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("evds_macro_cpi.json"))
    )

    out = evds_macro.fetch(keyed_ctx)
    assert [t for t, _ in out] == ["price_index"]
    assert route.call_count == 1
    req = route.calls[0].request
    assert req.headers["key"] == "test"
    assert "series=TP.FG.J0&startDate=01-01-2010&endDate=15-09-2026&type=json" in str(req.url)

    rows = out[0][1]
    assert len(rows) == 4  # null value skipped
    assert all(COLS == set(r) for r in rows)
    assert all(
        r["country_iso3"] == "TUR"
        and r["source"] == "tcmb_evds"
        and r["indicator"] == "cpi_index"
        and r["unit"] == "index 2003=100"
        for r in rows
    )
    by_date = {r["period_date"]: r["value"] for r in rows}
    assert by_date[date(2010, 1, 1)] == Decimal("174.07")
    assert by_date[date(2026, 7, 1)] == Decimal("3128.41")
    assert by_date[date(2026, 8, 15)] == Decimal("3150.02")  # dd-mm-yyyy form
    assert date(2026, 8, 1) not in by_date


@respx.mock
def test_fetch_skips_bad_items(keyed_ctx):
    payload = fixture_json("evds_macro_cpi.json")
    payload["items"].append({"Tarih": "garbage", "TP_FG_J0": "1"})
    payload["items"].append("not-an-object")
    payload["items"].append({"Tarih": "2026-9", "TP_FG_J0": "n/a"})
    respx.get(url__regex=EVDS_RE).mock(return_value=httpx.Response(200, json=payload))
    rows = evds_macro.fetch(keyed_ctx)[0][1]
    assert len(rows) == 4


@respx.mock
def test_fetch_raises_on_html_or_empty(keyed_ctx):
    respx.get(url__regex=EVDS_RE).mock(
        return_value=httpx.Response(200, text="<!DOCTYPE html><html></html>")
    )
    with pytest.raises(ValueError, match="non-JSON"):
        evds_macro.fetch(keyed_ctx)

    respx.get(url__regex=EVDS_RE).mock(return_value=httpx.Response(200, json={"items": []}))
    with pytest.raises(ValueError, match="no usable"):
        evds_macro.fetch(keyed_ctx)

    respx.get(url__regex=EVDS_RE).mock(return_value=httpx.Response(401, text="Invalid API Key"))
    with pytest.raises(httpx.HTTPStatusError):
        evds_macro.fetch(keyed_ctx)


def test_fetch_requires_key(ctx):
    with pytest.raises(ValueError, match="EVDS_API_KEY"):
        evds_macro.fetch(ctx)


def test_parse_period_variants():
    p = evds_macro._parse_period
    assert p("2010-1") == date(2010, 1, 1)
    assert p("2010-12") == date(2010, 12, 1)
    assert p("2010-03-07") == date(2010, 3, 7)
    assert p("07-03-2010") == date(2010, 3, 7)
    assert p("2010-13") is None
    assert p("") is None
    assert p(None) is None

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import fred
from tests.conftest import fixture_json

RESERVES_RE = r"https://api\.stlouisfed\.org/fred/series/observations\?.*series_id=TRESEGUSM052N.*"
FEDFUNDS_RE = r"https://api\.stlouisfed\.org/fred/series/observations\?.*series_id=FEDFUNDS.*"
CPI_RE = r"https://api\.stlouisfed\.org/fred/series/observations\?.*series_id=CPIAUCSL.*"

RESERVES_COLS = {"period_date", "country_iso3", "country", "metric", "value_usd", "source"}
PRICE_INDEX_COLS = {"period_date", "country_iso3", "indicator", "value", "unit", "source"}


@pytest.fixture
def keyed_ctx(ctx):
    ctx.cfg["env"]["FRED_API_KEY"] = "test"
    return ctx


def _mock_all():
    return (
        respx.get(url__regex=RESERVES_RE).mock(
            return_value=httpx.Response(200, json=fixture_json("fred_tresegusm052n.json"))
        ),
        respx.get(url__regex=FEDFUNDS_RE).mock(
            return_value=httpx.Response(200, json=fixture_json("fred_fedfunds.json"))
        ),
        respx.get(url__regex=CPI_RE).mock(
            return_value=httpx.Response(200, json=fixture_json("fred_cpiaucsl.json"))
        ),
    )


def test_source_metadata():
    assert fred.SOURCE.name == "fred"
    assert fred.SOURCE.interval == 86400
    assert fred.SOURCE.requires_env == ["FRED_API_KEY"]
    assert fred.SOURCE.tables == ["reserves", "price_index"]
    assert fred.SOURCE.backfill is None


@respx.mock
def test_fetch_maps_series_to_tables(keyed_ctx):
    reserves_route, fedfunds_route, cpi_route = _mock_all()

    out = fred.fetch(keyed_ctx)
    tables = dict(out)
    assert [t for t, _ in out] == ["reserves", "price_index"]
    assert reserves_route.call_count == 1
    assert fedfunds_route.call_count == 1
    assert cpi_route.call_count == 1

    params = reserves_route.calls[0].request.url.params
    assert params["api_key"] == "test"
    assert params["file_type"] == "json"
    assert params["observation_start"] == "1990-01-01"

    reserves = tables["reserves"]
    assert len(reserves) == 3  # "." observation skipped
    assert all(RESERVES_COLS == set(r) for r in reserves)
    assert {r["period_date"] for r in reserves} == {
        date(2026, 4, 1), date(2026, 5, 1), date(2026, 7, 1)
    }
    jul = next(r for r in reserves if r["period_date"] == date(2026, 7, 1))
    assert jul == {
        "period_date": date(2026, 7, 1),
        "country_iso3": "USA",
        "country": "United States",
        "metric": "ex_gold",
        "value_usd": Decimal("246030000000"),
        "source": "fred",
    }

    pi = tables["price_index"]
    assert len(pi) == 5  # 3 fed funds + 2 CPI (bad date skipped)
    assert all(PRICE_INDEX_COLS == set(r) for r in pi)
    assert all(r["country_iso3"] == "USA" and r["source"] == "fred" for r in pi)
    ff = [r for r in pi if r["indicator"] == "policy_rate_pct"]
    assert len(ff) == 3 and all(r["unit"] == "%" for r in ff)
    assert next(r for r in ff if r["period_date"] == date(2026, 8, 1))["value"] == Decimal("3.62")
    cpi = [r for r in pi if r["indicator"] == "cpi_index"]
    assert len(cpi) == 2 and all(r["unit"] == "index 1982-84=100" for r in cpi)
    assert next(r for r in cpi if r["period_date"] == date(2026, 6, 1))["value"] == Decimal(
        "327.114"
    )


@respx.mock
def test_fetch_keeps_other_series_when_one_fails(keyed_ctx):
    respx.get(url__regex=RESERVES_RE).mock(return_value=httpx.Response(500, text="boom"))
    respx.get(url__regex=FEDFUNDS_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("fred_fedfunds.json"))
    )
    respx.get(url__regex=CPI_RE).mock(
        return_value=httpx.Response(200, json={"error_code": 400, "error_message": "Bad Request"})
    )

    tables = dict(fred.fetch(keyed_ctx))
    assert tables["reserves"] == []
    assert len(tables["price_index"]) == 3
    assert {r["indicator"] for r in tables["price_index"]} == {"policy_rate_pct"}


@respx.mock
def test_fetch_raises_when_every_series_fails(keyed_ctx):
    respx.get(url__regex=RESERVES_RE).mock(return_value=httpx.Response(500, text="boom"))
    respx.get(url__regex=FEDFUNDS_RE).mock(return_value=httpx.Response(503, text="boom"))
    respx.get(url__regex=CPI_RE).mock(return_value=httpx.Response(200, json={"nope": []}))
    with pytest.raises(ValueError, match="every series request failed"):
        fred.fetch(keyed_ctx)


def test_fetch_requires_key(ctx):
    with pytest.raises(ValueError, match="FRED_API_KEY"):
        fred.fetch(ctx)


def test_parse_value_variants():
    assert fred._parse_value(".") is None
    assert fred._parse_value("") is None
    assert fred._parse_value(None) is None
    assert fred._parse_value("abc") is None
    assert fred._parse_value("3.5") == Decimal("3.5")
    assert fred._parse_value(2) == Decimal("2")

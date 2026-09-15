from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import eia
from tests.conftest import fixture_json

GND = r"https://api\.eia\.gov/v2/petroleum/pri/gnd/data/\?.*"
FUT = r"https://api\.eia\.gov/v2/natural-gas/pri/fut/data/\?.*"
SPT = r"https://api\.eia\.gov/v2/petroleum/pri/spt/data/\?.*"

FUEL_COLS = {
    "period_date", "country_iso2", "region", "fuel_type", "price", "currency", "unit", "source"
}
COMMODITY_COLS = {"period_date", "commodity", "price", "unit", "source"}


@pytest.fixture
def keyed_ctx(ctx):
    ctx.cfg["env"]["EIA_API_KEY"] = "test"
    return ctx


def _mock_all():
    return {
        "gasoline": respx.get(url__regex=GND + "EMM_EPMR_PTE_NUS_DPG.*").mock(
            return_value=httpx.Response(200, json=fixture_json("eia_gasoline.json"))
        ),
        "diesel": respx.get(url__regex=GND + "EMD_EPD2D_PTE_NUS_DPG.*").mock(
            return_value=httpx.Response(200, json=fixture_json("eia_diesel.json"))
        ),
        "henry_hub": respx.get(url__regex=FUT + "RNGWHHD.*").mock(
            return_value=httpx.Response(200, json=fixture_json("eia_henry_hub.json"))
        ),
        "brent": respx.get(url__regex=SPT + "RBRTE.*").mock(
            return_value=httpx.Response(200, json=fixture_json("eia_brent.json"))
        ),
        "wti": respx.get(url__regex=SPT + "RWTC.*").mock(
            return_value=httpx.Response(200, json=fixture_json("eia_wti.json"))
        ),
    }


def test_source_metadata():
    assert eia.SOURCE.name == "eia"
    assert eia.SOURCE.interval == 86400
    assert eia.SOURCE.requires_env == ["EIA_API_KEY"]
    assert eia.SOURCE.tables == ["fuel_price", "commodity_price"]
    assert eia.SOURCE.backfill is None


@respx.mock
def test_fetch_maps_series(keyed_ctx):
    routes = _mock_all()

    out = eia.fetch(keyed_ctx)
    tables = dict(out)
    assert [t for t, _ in out] == ["fuel_price", "commodity_price"]
    assert all(r.call_count == 1 for r in routes.values())

    params = routes["henry_hub"].calls[0].request.url.params
    assert params["api_key"] == "test"
    assert params["frequency"] == "daily"
    assert params["data[0]"] == "value"
    assert params["facets[series][]"] == "RNGWHHD"
    assert params["sort[0][column]"] == "period"
    assert params["sort[0][direction]"] == "desc"
    assert params["length"] == "5000"
    assert routes["gasoline"].calls[0].request.url.params["frequency"] == "weekly"

    fuel = tables["fuel_price"]
    assert len(fuel) == 4  # null gasoline value skipped
    assert all(FUEL_COLS == set(r) for r in fuel)
    assert all(
        r["country_iso2"] == "US"
        and r["region"] == ""
        and r["currency"] == "USD"
        and r["unit"] == "USD/gal"
        and r["source"] == "eia"
        for r in fuel
    )
    petrol = next(
        r
        for r in fuel
        if r["fuel_type"] == "petrol_regular" and r["period_date"] == date(2026, 9, 7)
    )
    assert petrol["price"] == Decimal("3.199")
    diesel = next(
        r for r in fuel if r["fuel_type"] == "diesel" and r["period_date"] == date(2026, 8, 31)
    )
    assert diesel["price"] == Decimal("3.688")

    comm = tables["commodity_price"]
    assert len(comm) == 7
    assert all(COMMODITY_COLS == set(r) for r in comm)
    assert all(r["source"] == "eia" for r in comm)
    hh = [r for r in comm if r["commodity"] == "henry_hub"]
    assert len(hh) == 3 and all(r["unit"] == "USD/MMBtu" for r in hh)
    hh_latest = next(r for r in hh if r["period_date"] == date(2026, 9, 11))
    assert hh_latest["price"] == Decimal("2.87")
    brent = next(
        r for r in comm if r["commodity"] == "brent_spot" and r["period_date"] == date(2026, 9, 10)
    )
    assert brent["price"] == Decimal("66.90") and brent["unit"] == "USD/bbl"
    wti = next(
        r for r in comm if r["commodity"] == "wti_spot" and r["period_date"] == date(2026, 9, 11)
    )
    assert wti["price"] == Decimal("63.15") and wti["unit"] == "USD/bbl"


@respx.mock
def test_fetch_keeps_other_series_when_one_fails(keyed_ctx):
    routes = _mock_all()
    routes["brent"].mock(return_value=httpx.Response(500, text="boom"))
    routes["wti"].mock(
        return_value=httpx.Response(200, json={"error": "invalid api_key", "code": 403})
    )

    tables = dict(eia.fetch(keyed_ctx))
    assert len(tables["fuel_price"]) == 4
    assert {r["commodity"] for r in tables["commodity_price"]} == {"henry_hub"}


@respx.mock
def test_fetch_skips_bad_records_and_duplicates(keyed_ctx):
    routes = _mock_all()
    payload = fixture_json("eia_henry_hub.json")
    payload["response"]["data"].append(
        {"period": "2026-09-11", "value": "9.99", "series": "RNGWHHD"}
    )
    payload["response"]["data"].append({"period": "bad", "value": "1", "series": "RNGWHHD"})
    payload["response"]["data"].append("junk")
    routes["henry_hub"].mock(return_value=httpx.Response(200, json=payload))

    hh = [r for r in dict(eia.fetch(keyed_ctx))["commodity_price"] if r["commodity"] == "henry_hub"]
    assert len(hh) == 3
    assert next(r for r in hh if r["period_date"] == date(2026, 9, 11))["price"] == Decimal("2.87")


@respx.mock
def test_fetch_raises_when_every_series_fails(keyed_ctx):
    respx.get(url__regex=r"https://api\.eia\.gov/.*").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(ValueError, match="every series request failed"):
        eia.fetch(keyed_ctx)


def test_fetch_requires_key(ctx):
    with pytest.raises(ValueError, match="EIA_API_KEY"):
        eia.fetch(ctx)

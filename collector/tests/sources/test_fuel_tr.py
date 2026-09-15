from __future__ import annotations

from datetime import date

import httpx
import respx

from mymon_collector.sources import fuel_tr
from tests.conftest import fixture_text


def _url(slug: str) -> str:
    return fuel_tr.BASE_URL.format(slug=slug)


def test_fuel_type_mapping():
    assert fuel_tr.fuel_type_for("V/Max Kurşunsuz 95") == "petrol95"
    assert fuel_tr.fuel_type_for("V/Max Diesel") == "diesel"
    assert fuel_tr.fuel_type_for("PO/gaz Otogaz") == "lpg"
    assert fuel_tr.fuel_type_for("Gazyağı") is None
    assert fuel_tr.fuel_type_for("Şehir") is None


def test_parse_page_prefers_avrupa():
    prices = fuel_tr.parse_page(fixture_text("fuel_tr_istanbul.html"), "AVRUPA")
    assert prices == {"petrol95": 80.26, "diesel": 95.60, "lpg": 34.99}
    anadolu = fuel_tr.parse_page(fixture_text("fuel_tr_istanbul.html"), "ANADOLU")
    assert anadolu["petrol95"] == 80.12


@respx.mock
def test_fetch_three_provinces(ctx):
    for slug in ("istanbul", "ankara", "izmir"):
        respx.get(_url(slug)).mock(
            return_value=httpx.Response(200, text=fixture_text(f"fuel_tr_{slug}.html"))
        )

    out = fuel_tr.fetch(ctx)
    assert [t for t, _ in out] == ["fuel_price"]
    rows = out[0][1]
    assert len(rows) == 9  # 3 provinces x petrol95/diesel/lpg

    pk = {"period_date", "country_iso2", "region", "fuel_type", "source"}
    for r in rows:
        assert pk <= set(r)
        assert r["country_iso2"] == "TR"
        assert r["currency"] == "TRY" and r["unit"] == "TRY/L" and r["source"] == "petrolofisi"
        assert r["period_date"] == date(2026, 9, 15)  # ctx.now 12:00 UTC -> 15:00 Istanbul

    by_key = {(r["region"], r["fuel_type"]): r["price"] for r in rows}
    assert by_key[("Istanbul", "petrol95")] == 80.26
    assert by_key[("Ankara", "diesel")] == 96.75
    assert by_key[("Izmir", "lpg")] == 34.99


@respx.mock
def test_fetch_survives_one_failed_province(ctx):
    respx.get(_url("istanbul")).mock(return_value=httpx.Response(500))
    for slug in ("ankara", "izmir"):
        respx.get(_url(slug)).mock(
            return_value=httpx.Response(200, text=fixture_text(f"fuel_tr_{slug}.html"))
        )
    rows = fuel_tr.fetch(ctx)[0][1]
    assert {r["region"] for r in rows} == {"Ankara", "Izmir"}
    assert len(rows) == 6


@respx.mock
def test_fetch_raises_when_all_fail(ctx):
    for slug in ("istanbul", "ankara", "izmir"):
        respx.get(_url(slug)).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    try:
        fuel_tr.fetch(ctx)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

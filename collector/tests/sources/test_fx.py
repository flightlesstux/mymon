from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import fx
from tests.conftest import fixture_bytes, fixture_json

PK = {"ts", "base", "quote", "source"}


def _mock_tcmb():
    respx.get(fx.TCMB_TODAY).mock(
        return_value=httpx.Response(
            200,
            content=fixture_bytes("fx_tcmb_today.xml"),
            headers={"content-type": "application/xml"},
        )
    )


def _mock_latest():
    respx.get(url__regex=r"https://api\.frankfurter\.dev/v1/latest\?.*base=USD.*").mock(
        return_value=httpx.Response(200, json=fixture_json("fx_frankfurter_latest.json"))
    )


def test_source_metadata():
    assert fx.SOURCE.name == "fx"
    assert fx.SOURCE.interval == 3600
    assert fx.SOURCE.tables == ["fx_rate"]
    assert fx.SOURCE.backfill is not None


@respx.mock
def test_fetch_merges_frankfurter_and_tcmb(ctx):
    _mock_latest()
    _mock_tcmb()

    out = fx.fetch(ctx)

    assert [t for t, _ in out] == ["fx_rate"]
    rows = out[0][1]
    frank = [r for r in rows if r["source"] == "frankfurter"]
    tcmb = [r for r in rows if r["source"] == "tcmb"]
    assert len(frank) == 16
    # fixture has 9 kept currencies, XDR has an empty ForexSelling and is skipped
    assert len(tcmb) == 8
    assert all(PK <= r.keys() for r in rows)

    eur = next(r for r in frank if r["quote"] == "EUR")
    assert eur["base"] == "USD"
    assert eur["rate"] == Decimal("0.86663")
    assert eur["ts"] == datetime(2026, 9, 15, tzinfo=UTC)

    usd_try = next(r for r in tcmb if r["base"] == "USD")
    assert usd_try["quote"] == "TRY"
    assert usd_try["rate"] == Decimal("48.6460")
    assert usd_try["ts"] == datetime(2026, 9, 15, tzinfo=UTC)

    # JPY is quoted per 100 units in the TCMB bulletin
    jpy = next(r for r in tcmb if r["base"] == "JPY")
    assert jpy["rate"] == Decimal("31.4777") / 100
    assert not any(r["base"] == "XDR" for r in tcmb)


@respx.mock
def test_fetch_survives_one_provider_failure(ctx):
    _mock_latest()
    respx.get(fx.TCMB_TODAY).mock(return_value=httpx.Response(503))

    out = fx.fetch(ctx)
    rows = out[0][1]
    assert len(rows) == 16
    assert {r["source"] for r in rows} == {"frankfurter"}


@respx.mock
def test_fetch_raises_when_both_fail(ctx):
    respx.get(url__regex=r"https://api\.frankfurter\.(dev|app)/.*").mock(
        return_value=httpx.Response(500)
    )
    respx.get(fx.TCMB_TODAY).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError):
        fx.fetch(ctx)


@respx.mock
def test_frankfurter_legacy_fallback_on_404(ctx):
    respx.get(url__regex=r"https://api\.frankfurter\.dev/v1/latest.*").mock(
        return_value=httpx.Response(404)
    )
    respx.get(url__regex=r"https://api\.frankfurter\.app/latest.*").mock(
        return_value=httpx.Response(200, json=fixture_json("fx_frankfurter_latest.json"))
    )
    _mock_tcmb()
    rows = fx.fetch(ctx)[0][1]
    assert len([r for r in rows if r["source"] == "frankfurter"]) == 16


def test_chunks_cover_range_in_five_year_blocks():
    from datetime import date

    chunks = fx._chunks(date(1999, 1, 4), date(2026, 9, 15))
    assert chunks[0] == (date(1999, 1, 4), date(2003, 12, 31))
    assert chunks[1] == (date(2004, 1, 1), date(2008, 12, 31))
    assert chunks[-1][1] == date(2026, 9, 15)
    assert len(chunks) == 6


@respx.mock
def test_backfill_pages_through_history(ctx):
    range_route = respx.get(
        url__regex=r"https://api\.frankfurter\.dev/v1/\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}\?.*"
    ).mock(return_value=httpx.Response(200, json=fixture_json("fx_frankfurter_range.json")))
    _mock_tcmb()

    out = fx.backfill(ctx)

    assert [t for t, _ in out] == ["fx_rate"]
    rows = out[0][1]
    assert range_route.call_count == 6
    frank = [r for r in rows if r["source"] == "frankfurter"]
    # 7 days x 16 quotes per chunk, same fixture served 6 times -> duplicates are fine (upsert)
    assert len(frank) == 6 * 7 * 16
    assert all(PK <= r.keys() for r in rows)
    first = next(
        r for r in frank if r["ts"] == datetime(2004, 1, 2, tzinfo=UTC) and r["quote"] == "EUR"
    )
    assert first["rate"] == Decimal("0.79416")
    assert first["base"] == "USD"
    assert any(r["source"] == "tcmb" for r in rows)

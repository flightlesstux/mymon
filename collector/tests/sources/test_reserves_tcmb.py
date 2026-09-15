from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import reserves_tcmb as tcmb
from tests.conftest import fixture_json

COLS = {"period_date", "country_iso3", "country", "metric", "value_usd", "source"}
EVDS_RE = r"https://evds2\.tcmb\.gov\.tr/service/evds/.*"


def test_source_metadata():
    assert tcmb.SOURCE.name == "reserves_tcmb"
    assert tcmb.SOURCE.interval == 86400
    assert tcmb.SOURCE.requires_env == ["EVDS_API_KEY"]
    assert tcmb.SOURCE.tables == ["reserves"]
    assert tcmb.SOURCE.backfill is None


def test_build_url():
    url = tcmb.build_url(datetime(2026, 9, 15, tzinfo=UTC))
    assert url == (
        "https://evds2.tcmb.gov.tr/service/evds/"
        "series=TP.AB.A01-TP.AB.A02-TP.AB.A03&startDate=01-01-2000"
        "&endDate=15-09-2026&type=json"
    )


def test_fetch_without_key_raises(ctx):
    with pytest.raises(RuntimeError, match="EVDS_API_KEY"):
        tcmb.fetch(ctx)


@respx.mock
def test_fetch(ctx):
    ctx.cfg["env"]["EVDS_API_KEY"] = "x"
    route = respx.get(url__regex=EVDS_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("reserves_tcmb_evds.json"))
    )

    out = tcmb.fetch(ctx)
    assert route.call_count == 1
    assert route.calls[0].request.headers["key"] == "x"

    assert [t for t, _ in out] == ["reserves"]
    rows = out[0][1]
    assert all(COLS == set(r) for r in rows)
    assert all(
        r["country_iso3"] == "TUR" and r["country"] == "Turkiye" and r["source"] == "tcmb_evds"
        for r in rows
    )

    # third item has an unparseable date and is skipped entirely; second item has a
    # null TP_AB_A02 (gold) so only gross_fx and total are emitted for it.
    assert len(rows) == 5

    by_key = {(r["period_date"], r["metric"]): r["value_usd"] for r in rows}
    million = Decimal(1_000_000)
    assert by_key[(date(2000, 1, 7), "gross_fx")] == Decimal("23345.6") * million
    assert by_key[(date(2000, 1, 7), "gold")] == Decimal("1050.2") * million
    assert by_key[(date(2000, 1, 7), "total")] == Decimal("24395.8") * million
    assert by_key[(date(2000, 1, 14), "gross_fx")] == Decimal("23410.1") * million
    assert (date(2000, 1, 14), "gold") not in by_key
    assert by_key[(date(2000, 1, 14), "total")] == Decimal("24460.3") * million


def test_parse_items_skips_bad_date():
    rows = tcmb.parse_items(
        [
            {"Tarih": "not-a-date", "TP_AB_A01": "1", "TP_AB_A02": "1", "TP_AB_A03": "2"},
        ]
    )
    assert rows == []


@respx.mock
def test_fetch_raises_on_missing_items(ctx):
    ctx.cfg["env"]["EVDS_API_KEY"] = "x"
    respx.get(url__regex=EVDS_RE).mock(return_value=httpx.Response(200, json={"foo": "bar"}))
    with pytest.raises(ValueError, match="no 'items'"):
        tcmb.fetch(ctx)

    respx.get(url__regex=EVDS_RE).mock(return_value=httpx.Response(200, json={"items": []}))
    with pytest.raises(ValueError, match="no usable"):
        tcmb.fetch(ctx)

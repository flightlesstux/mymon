from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import reserves_ecb as ecb
from tests.conftest import fixture_text

COLS = {"period_date", "country_iso3", "country", "metric", "value_usd", "source"}


def test_source_metadata():
    assert ecb.SOURCE.name == "reserves_ecb"
    assert ecb.SOURCE.interval == 86400
    assert ecb.SOURCE.requires_env == []
    assert ecb.SOURCE.tables == ["reserves"]
    assert ecb.SOURCE.backfill is None


def test_period_end():
    assert ecb.period_end("1999-Q1") == date(1999, 3, 31)
    assert ecb.period_end("2025-Q3") == date(2025, 9, 30)
    assert ecb.period_end("2026-Q1") == date(2026, 3, 31)


@respx.mock
def test_fetch(ctx):
    route = respx.get(ecb.DATA_URL).mock(
        return_value=httpx.Response(200, text=fixture_text("reserves_ecb_bps.csv"))
    )

    out = ecb.fetch(ctx)
    assert route.call_count == 1
    assert route.calls[0].request.url.params["format"] == "csvdata"

    assert [t for t, _ in out] == ["reserves"]
    rows = out[0][1]
    # 5 data lines in the fixture: one bad TIME_PERIOD and one blank OBS_VALUE are skipped
    assert len(rows) == 3
    assert all(COLS == set(r) for r in rows)
    assert all(
        r["country_iso3"] == "EMU"
        and r["country"] == "Euro area"
        and r["metric"] == "total"
        and r["source"] == "ecb_eur"
        for r in rows
    )

    by_period = {r["period_date"]: r["value_usd"] for r in rows}
    assert by_period[date(1999, 3, 31)] == Decimal("381693.2732") * Decimal(10) ** 6
    assert by_period[date(2025, 9, 30)] == Decimal("1622200.6811") * Decimal(10) ** 6
    assert by_period[date(2026, 3, 31)] == Decimal("1908096.6995") * Decimal(10) ** 6
    assert date(1999, 6, 30) not in by_period  # blank OBS_VALUE row skipped


@respx.mock
def test_fetch_raises_on_http_error_or_empty(ctx):
    respx.get(ecb.DATA_URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        ecb.fetch(ctx)

    respx.get(ecb.DATA_URL).mock(
        return_value=httpx.Response(
            200,
            text="KEY,FREQ,TIME_PERIOD,OBS_VALUE,UNIT_MULT\nX,Q,1999-Q1,,6\n",
        )
    )
    with pytest.raises(ValueError, match="no usable"):
        ecb.fetch(ctx)


def test_parse_csv_rejects_missing_time_period_column():
    with pytest.raises(ValueError, match="missing TIME_PERIOD"):
        ecb._parse_csv("a,b,c\n1,2,3\n")

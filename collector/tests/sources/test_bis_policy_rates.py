from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import bis_policy_rates as bis
from tests.conftest import fixture_text

BIS_RE = r"https://stats\.bis\.org/api/v1/data/WS_CBPOL/M\.\.\?.*"
COLS = {"period_date", "country_iso3", "indicator", "value", "unit", "source"}


def test_source_metadata():
    assert bis.SOURCE.name == "bis_policy_rates"
    assert bis.SOURCE.interval == 86400
    assert bis.SOURCE.requires_env == []
    assert bis.SOURCE.tables == ["price_index"]
    assert bis.SOURCE.backfill is None


@respx.mock
def test_fetch_dataonly_csv(ctx):
    route = respx.get(url__regex=BIS_RE).mock(
        return_value=httpx.Response(
            200,
            text=fixture_text("bis_policy_rates_cbpol.csv"),
            headers={"content-type": "text/csv;charset=UTF-8"},
        )
    )

    out = bis.fetch(ctx)
    assert [t for t, _ in out] == ["price_index"]
    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["format"] == "csv"
    assert params["lastNObservations"] == "240"
    assert params["detail"] == "dataonly"

    rows = out[0][1]
    assert len(rows) == 15  # 5 areas x 3 months
    assert all(COLS == set(r) for r in rows)
    assert all(
        r["indicator"] == "policy_rate_pct" and r["unit"] == "%" and r["source"] == "bis"
        for r in rows
    )
    assert {r["country_iso3"] for r in rows} == {"BRA", "GBR", "EMU", "TUR", "USA"}
    assert {r["period_date"] for r in rows} == {
        date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)
    }
    by_key = {(r["country_iso3"], r["period_date"]): r["value"] for r in rows}
    assert by_key[("BRA", date(2026, 8, 1))] == Decimal("14")
    assert by_key[("TUR", date(2026, 7, 1))] == Decimal("37")
    assert by_key[("USA", date(2026, 6, 1))] == Decimal("3.625")
    assert by_key[("EMU", date(2026, 8, 1))] == Decimal("2.25")


@respx.mock
def test_fetch_full_attribute_csv(ctx):
    # The un-trimmed layout carries long quoted text columns; header-based parsing must cope.
    respx.get(url__regex=BIS_RE).mock(
        return_value=httpx.Response(200, text=fixture_text("bis_policy_rates_cbpol_full.csv"))
    )
    rows = bis.fetch(ctx)[0][1]
    assert len(rows) == 15
    gb = next(
        r for r in rows if r["country_iso3"] == "GBR" and r["period_date"] == date(2026, 8, 1)
    )
    assert gb["value"] == Decimal("3.75")


def test_rows_from_csv_skips_unknown_area_and_bad_rows():
    text = (
        "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\n"
        "M,US,2026-08,3.625\n"
        "M,ZZ,2026-08,1\n"
        "M,US,garbage,1\n"
        "M,US,2026-07,\n"
        "M,US,2026-06,n/a\n"
        "M,TR,2026,37\n"
    )
    rows = bis._rows_from_csv(text)
    assert [(r["country_iso3"], r["period_date"], r["value"]) for r in rows] == [
        ("USA", date(2026, 8, 1), Decimal("3.625")),
        ("TUR", date(2026, 1, 1), Decimal("37")),
    ]


def test_rows_from_csv_rejects_unknown_header():
    with pytest.raises(ValueError, match="unexpected CSV header"):
        bis._rows_from_csv("a,b,c\n1,2,3\n")


@respx.mock
def test_fetch_raises_on_http_error_or_empty(ctx):
    respx.get(url__regex=BIS_RE).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        bis.fetch(ctx)

    respx.get(url__regex=BIS_RE).mock(
        return_value=httpx.Response(200, text="FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\n")
    )
    with pytest.raises(ValueError, match="no usable"):
        bis.fetch(ctx)


def test_iso_map_covers_live_areas():
    live = (
        "AR AT AU BE BR CA CH CL CN CO CZ DE DK ES FR GB GR HK HR HU ID IL IN IS IT JP KR KW "
        "MA MK MX MY NL NO NZ PE PH PL PT RO RS RU SA SE TH TR US XM ZA"
    ).split()
    assert all(a in bis.ISO2_TO_ISO3 for a in live)
    assert bis.ISO2_TO_ISO3["XM"] == "EMU"

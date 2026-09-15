from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import respx

from mymon_collector.sources import reserves_worldbank as wb
from tests.conftest import fixture_json

COLS = {"period_date", "country_iso3", "country", "metric", "value_usd", "source"}
TOTL_URL = "https://api.worldbank.org/v2/country/all/indicator/FI.RES.TOTL.CD"
XGLD_URL = "https://api.worldbank.org/v2/country/all/indicator/FI.RES.XGLD.CD"


def test_source_metadata():
    assert wb.SOURCE.name == "reserves_worldbank"
    assert wb.SOURCE.interval == 86400
    assert wb.SOURCE.requires_env == []
    assert wb.SOURCE.tables == ["reserves"]
    assert wb.SOURCE.backfill is None


@respx.mock
def test_fetch(ctx):
    respx.get(TOTL_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("reserves_worldbank_totl.json"))
    )
    respx.get(XGLD_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("reserves_worldbank_xgld.json"))
    )

    out = wb.fetch(ctx)
    assert [t for t, _ in out] == ["reserves"]
    rows = out[0][1]
    assert all(COLS == set(r) for r in rows)
    assert all(r["source"] == "worldbank" for r in rows)

    # Aggregates: EMU/WLD kept, EUU (an aggregate not in the keep-list) dropped,
    # and the blank-iso3 "High income" record dropped too.
    isos = {r["country_iso3"] for r in rows}
    assert "EMU" in isos
    assert "WLD" not in isos  # WLD total/xgld value is null in the fixture -> no row
    assert "EUU" not in isos
    assert "" not in isos

    by_key = {(r["country_iso3"], r["period_date"], r["metric"]): r["value_usd"] for r in rows}

    # total for EMU 2024
    assert by_key[("EMU", date(2024, 12, 31), "total")] == Decimal("1449054959888.77")
    # ex_gold for EMU 2024
    assert by_key[("EMU", date(2024, 12, 31), "ex_gold")] == Decimal("546006313388.768")
    # derived gold = total - ex_gold for EMU 2024
    assert by_key[("EMU", date(2024, 12, 31), "gold")] == (
        Decimal("1449054959888.77") - Decimal("546006313388.768")
    )

    # ABW has both indicators too, so gold is derived the same way
    assert by_key[("ABW", date(2024, 12, 31), "total")] == Decimal("1902250220")
    assert by_key[("ABW", date(2024, 12, 31), "ex_gold")] == Decimal("1641340220")
    assert by_key[("ABW", date(2024, 12, 31), "gold")] == Decimal("260910000")

    # USA only appears with a total (no matching xgld record) -> no derived gold row
    assert ("USA", date(2024, 12, 31), "gold") not in by_key
    assert by_key[("USA", date(2024, 12, 31), "total")] == Decimal("910036546651.5")

    # TUR has both indicators across several years
    assert by_key[("TUR", date(2023, 12, 31), "total")] == Decimal("140868480001.696")
    assert by_key[("TUR", date(2023, 12, 31), "ex_gold")] == Decimal("92703190401.6959")


@respx.mock
def test_fetch_raises_on_bad_shape(ctx):
    respx.get(TOTL_URL).mock(return_value=httpx.Response(200, json={"not": "a list"}))
    respx.get(XGLD_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("reserves_worldbank_xgld.json"))
    )
    try:
        wb.fetch(ctx)
    except ValueError as exc:
        assert "unexpected response shape" in str(exc)
    else:
        raise AssertionError("expected ValueError")

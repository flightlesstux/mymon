from datetime import date

import httpx
import pytest
import respx

from mymon_collector.sources import co2 as mod
from tests.conftest import fixture_text

PK = {"month"}


@respx.mock
def test_fetch(ctx):
    respx.get(mod.URL).mock(return_value=httpx.Response(200, text=fixture_text("co2_mm_mlo.csv")))
    out = mod.fetch(ctx)
    assert [t for t, _ in out] == ["co2_monthly"]
    rows = out[0][1]
    assert len(rows) == 7
    assert rows[0] == {"month": date(1958, 3, 1), "ppm": 315.71, "trend_ppm": 314.44}
    assert rows[-1] == {"month": date(2026, 8, 1), "ppm": 427.55, "trend_ppm": 429.51}
    sentinel = next(r for r in rows if r["month"] == date(1964, 2, 1))
    assert sentinel["ppm"] is None
    assert sentinel["trend_ppm"] is None
    assert all(PK <= r.keys() for r in rows)
    assert len({frozenset(r) for r in rows}) == 1
    assert mod.SOURCE.backfill is None


@respx.mock
def test_bad_header_raises(ctx):
    respx.get(mod.URL).mock(return_value=httpx.Response(200, text="# only\nfoo,bar\n1,2\n"))
    with pytest.raises(ValueError):
        mod.fetch(ctx)


@respx.mock
def test_skips_bad_row(ctx):
    text = fixture_text("co2_mm_mlo.csv") + "abc,13,x,1,2,3,4,5\n"
    respx.get(mod.URL).mock(return_value=httpx.Response(200, text=text))
    assert len(mod.fetch(ctx)[0][1]) == 7

from datetime import UTC, datetime

import httpx
import pytest
import respx

from mymon_collector.sources import space_weather as mod
from tests.conftest import fixture_json

PK = {"ts"}


def _mock_all():
    respx.get(mod.KP_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("space_weather_kp.json"))
    )
    respx.get(mod.WIND_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("space_weather_rtsw_wind.json"))
    )
    respx.get(mod.MAG_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("space_weather_rtsw_mag.json"))
    )


@respx.mock
def test_fetch(ctx):
    _mock_all()
    out = mod.fetch(ctx)
    assert [t for t, _ in out] == ["space_weather"]
    rows = out[0][1]
    # fixture has 4 entries from 2026-09-08 (outside 24h) and 3 from 2026-09-15
    assert len(rows) == 3
    assert [r["ts"] for r in rows] == [
        datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
    ]
    assert rows[-1]["kp"] == 0.67
    assert rows[0]["solar_wind_speed"] is None
    assert rows[0]["bz"] is None
    latest = rows[-1]
    assert latest["solar_wind_speed"] == pytest.approx(705.6)
    assert latest["solar_wind_density"] == pytest.approx(2.64)
    assert latest["bz"] == pytest.approx(-7.73)
    assert all(PK <= r.keys() for r in rows)
    assert len({frozenset(r) for r in rows}) == 1
    assert mod.SOURCE.backfill is None


@respx.mock
def test_fetch_wind_unavailable(ctx):
    _mock_all()
    respx.get(mod.WIND_URL).mock(return_value=httpx.Response(404))
    respx.get(mod.MAG_URL).mock(return_value=httpx.Response(404))
    rows = mod.fetch(ctx)[0][1]
    assert len(rows) == 3
    assert rows[-1]["solar_wind_speed"] is None
    assert rows[-1]["bz"] is None
    assert rows[-1]["kp"] == 0.67


@respx.mock
def test_fetch_header_row_layout(ctx):
    kp = [
        ["time_tag", "Kp", "a_running", "station_count"],
        ["2026-09-15 09:00:00.000", "2.33", "9", "8"],
        ["2026-09-15 12:00:00.000", "3.00", "15", "8"],
    ]
    respx.get(mod.KP_URL).mock(return_value=httpx.Response(200, json=kp))
    respx.get(mod.WIND_URL).mock(return_value=httpx.Response(404))
    respx.get(mod.MAG_URL).mock(return_value=httpx.Response(404))
    rows = mod.fetch(ctx)[0][1]
    assert len(rows) == 2
    assert rows[1]["ts"] == datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert rows[1]["kp"] == 3.0

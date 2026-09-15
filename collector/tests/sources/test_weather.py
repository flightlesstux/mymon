from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from mymon_collector.source import Ctx
from mymon_collector.sources import weather
from tests.conftest import fixture_json

FORECAST_RE = r"https://api\.open-meteo\.com/v1/forecast.*"
AIR_RE = r"https://air-quality-api\.open-meteo\.com/v1/air-quality.*"
ARCHIVE_RE = r"https://archive-api\.open-meteo\.com/v1/archive.*"

CURRENT_COLS = {
    "ts", "city", "temp_c", "feels_like_c", "humidity", "wind_kph", "wind_dir", "pressure_hpa",
    "precip_mm", "cloud_pct", "weather_code", "uv", "aqi_eu", "pm2_5", "pm10",
}
FORECAST_COLS = {
    "city", "day", "fetched_at", "tmin_c", "tmax_c", "precip_mm", "precip_prob", "weather_code"
}
DAILY_COLS = {"day", "city", "tmin_c", "tmax_c", "precip_mm", "wind_max_kph", "weather_code"}


@pytest.fixture
def ctx(cities) -> Ctx:
    # Fixtures were captured for the first three cities in config/cities.yml.
    three = [c for c in cities if c["name"] in ("Istanbul", "Ankara", "London")]
    assert [c["name"] for c in three] == ["Istanbul", "Ankara", "London"]
    with httpx.Client() as client:
        yield Ctx(
            http=client,
            cfg={"cities": three, "env": {}},
            now=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        )


def _tables(rows) -> dict[str, list[dict]]:
    return dict(rows)


def test_source_metadata():
    assert weather.SOURCE.name == "weather"
    assert weather.SOURCE.interval == 900
    assert weather.SOURCE.tables == ["weather_current", "weather_forecast", "weather_daily"]
    assert weather.SOURCE.backfill is weather.backfill
    assert weather.SOURCE.requires_env == []


@respx.mock
def test_fetch_merges_forecast_and_air_quality(ctx):
    fc_route = respx.get(url__regex=FORECAST_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_forecast.json"))
    )
    aq_route = respx.get(url__regex=AIR_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_airquality.json"))
    )

    out = weather.fetch(ctx)
    tables = _tables(out)

    assert [t for t, _ in out] == ["weather_current", "weather_forecast", "weather_daily"]
    assert fc_route.call_count == 1 and aq_route.call_count == 1

    # one request carries every city
    params = fc_route.calls[0].request.url.params
    assert params["latitude"] == "41.0082,39.9334,51.5074"
    assert params["longitude"] == "28.9784,32.8597,-0.1278"
    assert params["timezone"] == "UTC"
    assert params["wind_speed_unit"] == "kmh"
    assert params["forecast_days"] == "7"

    current = tables["weather_current"]
    assert len(current) == 3
    assert all(CURRENT_COLS == set(r) for r in current)
    ist = next(r for r in current if r["city"] == "Istanbul")
    assert ist["ts"] == datetime(2026, 9, 15, 18, 15, tzinfo=UTC)
    assert ist["temp_c"] == 19.9
    assert ist["feels_like_c"] == 19.2
    assert ist["humidity"] == 75
    assert ist["wind_kph"] == 16.8
    assert ist["weather_code"] == 2
    assert ist["aqi_eu"] == 28
    assert ist["pm2_5"] == 6.6
    assert ist["pm10"] == 12.3
    ldn = next(r for r in current if r["city"] == "London")
    assert ldn["temp_c"] == 20.8 and ldn["aqi_eu"] == 25

    forecast = tables["weather_forecast"]
    assert len(forecast) == 3 * 7
    assert all(FORECAST_COLS == set(r) for r in forecast)
    assert all(r["fetched_at"] == ctx.now for r in forecast)
    ist0 = next(r for r in forecast if r["city"] == "Istanbul" and r["day"] == date(2026, 9, 15))
    assert ist0["tmin_c"] == 16.1
    assert ist0["tmax_c"] == 22.9
    assert ist0["precip_prob"] == 3
    assert ist0["weather_code"] == 3
    assert {r["day"] for r in forecast if r["city"] == "Ankara"} == {
        date(2026, 9, d) for d in range(15, 22)
    }

    daily = tables["weather_daily"]
    assert len(daily) == 3 * 2
    assert all(DAILY_COLS == set(r) for r in daily)
    assert {r["day"] for r in daily} == {date(2026, 9, 15), date(2026, 9, 16)}
    ank = next(r for r in daily if r["city"] == "Ankara" and r["day"] == date(2026, 9, 15))
    assert ank["tmin_c"] == 11.0 and ank["tmax_c"] == 24.6 and ank["wind_max_kph"] is None


@respx.mock
def test_fetch_air_quality_failure_leaves_columns_none(ctx):
    respx.get(url__regex=FORECAST_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_forecast.json"))
    )
    respx.get(url__regex=AIR_RE).mock(return_value=httpx.Response(503, text="down"))

    tables = _tables(weather.fetch(ctx))
    current = tables["weather_current"]
    assert len(current) == 3
    assert all(r["aqi_eu"] is None and r["pm2_5"] is None and r["pm10"] is None for r in current)
    assert current[0]["temp_c"] == 19.9


@respx.mock
def test_fetch_single_city_object_payload(ctx):
    ctx.cfg["cities"] = ctx.cities[:1]
    respx.get(url__regex=FORECAST_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_forecast.json")[0])
    )
    respx.get(url__regex=AIR_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_airquality.json")[0])
    )

    tables = _tables(weather.fetch(ctx))
    assert len(tables["weather_current"]) == 1
    assert tables["weather_current"][0]["city"] == "Istanbul"
    assert tables["weather_current"][0]["aqi_eu"] == 28
    assert len(tables["weather_forecast"]) == 7
    assert len(tables["weather_daily"]) == 2


@respx.mock
def test_fetch_skips_bad_city_entry(ctx):
    payload = fixture_json("weather_forecast.json")
    payload[1]["current"]["time"] = "not-a-date"
    del payload[2]["daily"]
    respx.get(url__regex=FORECAST_RE).mock(return_value=httpx.Response(200, json=payload))
    respx.get(url__regex=AIR_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_airquality.json"))
    )

    tables = _tables(weather.fetch(ctx))
    assert [r["city"] for r in tables["weather_current"]] == ["Istanbul", "London"]
    assert {r["city"] for r in tables["weather_forecast"]} == {"Istanbul", "Ankara"}


@respx.mock
def test_fetch_raises_on_http_error(ctx):
    respx.get(url__regex=FORECAST_RE).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        weather.fetch(ctx)


@respx.mock
def test_backfill_archive(ctx):
    route = respx.get(url__regex=ARCHIVE_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_archive.json"))
    )

    out = weather.backfill(ctx)
    assert [t for t, _ in out] == ["weather_daily"]
    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["start_date"] == "2025-09-15"
    assert params["end_date"] == "2026-09-13"
    assert params["latitude"] == "41.0082,39.9334,51.5074"
    assert params["wind_speed_unit"] == "kmh"

    rows = out[0][1]
    assert len(rows) == 3 * 6
    assert all(DAILY_COLS == set(r) for r in rows)
    ist = next(r for r in rows if r["city"] == "Istanbul" and r["day"] == date(2026, 9, 8))
    assert ist["tmin_c"] == 18.6
    assert ist["tmax_c"] == 25.9
    assert ist["wind_max_kph"] == 21.3
    assert ist["weather_code"] == 2
    ldn = next(r for r in rows if r["city"] == "London" and r["day"] == date(2026, 9, 8))
    assert ldn["precip_mm"] == 19.5 and ldn["weather_code"] == 61


@respx.mock
def test_backfill_single_city_object_payload(ctx):
    ctx.cfg["cities"] = ctx.cities[:1]
    respx.get(url__regex=ARCHIVE_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("weather_archive.json")[0])
    )
    rows = weather.backfill(ctx)[0][1]
    assert len(rows) == 6
    assert {r["city"] for r in rows} == {"Istanbul"}

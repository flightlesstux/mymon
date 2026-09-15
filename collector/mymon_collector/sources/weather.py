"""Weather source: Open-Meteo current conditions, 7-day forecast, air quality and history.

Every call sends all configured cities in one request (comma-joined ``latitude``/``longitude``
lists). Open-Meteo answers with a JSON array in the same order as the request when several
locations are given, but with a bare object when only one is given; ``_as_list`` normalises both.

Tables:
- ``weather_current``  one row per city per poll (ts = the API's ``current.time`` in UTC),
  enriched with European AQI / PM values from the air-quality API when that call succeeds.
- ``weather_forecast`` one row per city per forecast day (7 days).
- ``weather_daily``    daily history; backfilled from the archive API (which lags ~2 days) and
  kept current from the first two days of the forecast ``daily`` block on every poll.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

CURRENT_VARS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,"
    "wind_direction_10m,surface_pressure,precipitation,cloud_cover,weather_code,uv_index"
)
FORECAST_DAILY_VARS = (
    "temperature_2m_min,temperature_2m_max,precipitation_sum,"
    "precipitation_probability_max,weather_code"
)
ARCHIVE_DAILY_VARS = (
    "temperature_2m_min,temperature_2m_max,precipitation_sum,wind_speed_10m_max,weather_code"
)
AIR_QUALITY_VARS = "european_aqi,pm2_5,pm10"

FORECAST_DAYS = 7
DAILY_FROM_FORECAST_DAYS = 2  # today + tomorrow keep weather_daily current between archive runs
BACKFILL_DAYS = 365
ARCHIVE_LAG_DAYS = 2


# --------------------------------------------------------------------------- helpers


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    f = _num(value)
    return None if f is None else int(f)


def _parse_ts(value: Any) -> datetime | None:
    """Open-Meteo emits naive ISO strings (``2026-09-15T18:15``) in the requested timezone."""
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def _parse_day(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _location_params(cities: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "latitude": ",".join(str(c["lat"]) for c in cities),
        "longitude": ",".join(str(c["lon"]) for c in cities),
    }


def _as_list(payload: Any) -> list[Any]:
    """Open-Meteo returns an object for one location and an array for several."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "error" in payload and payload.get("error") is True:
            raise ValueError(f"Open-Meteo error: {payload.get('reason', 'unknown')}")
        return [payload]
    raise ValueError(f"unexpected Open-Meteo payload type {type(payload).__name__}")


def _get(ctx: Ctx, url: str, params: dict[str, Any]) -> list[Any]:
    resp = ctx.http.get(url, params=params)
    resp.raise_for_status()
    return _as_list(resp.json())


def _zip_cities(
    cities: list[dict[str, Any]], items: list[Any], what: str
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Pair cities with response entries by position; missing entries become ``None``."""
    if len(items) != len(cities):
        log.warning(
            "%s: expected %d locations, got %d; pairing by position", what, len(cities), len(items)
        )
    paired: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for idx, city in enumerate(cities):
        item = items[idx] if idx < len(items) else None
        if item is not None and not isinstance(item, dict):
            log.warning("%s: entry %d for %s is not an object, skipped", what, idx, city["name"])
            item = None
        paired.append((city, item))
    return paired


def _daily_series(block: Any, city: str, what: str) -> list[tuple[date, int, dict[str, Any]]]:
    """Yield ``(day, index, block)`` for each parseable day in a ``daily`` block."""
    if not isinstance(block, dict) or not isinstance(block.get("time"), list):
        log.warning("%s: no daily block for %s, skipped", what, city)
        return []
    out: list[tuple[date, int, dict[str, Any]]] = []
    for idx, raw in enumerate(block["time"]):
        day = _parse_day(raw)
        if day is None:
            log.warning("%s: bad day %r for %s, skipped", what, raw, city)
            continue
        out.append((day, idx, block))
    return out


def _col(block: dict[str, Any], key: str, idx: int) -> Any:
    series = block.get(key)
    if isinstance(series, list) and idx < len(series):
        return series[idx]
    return None


# --------------------------------------------------------------------------- fetch


def _current_row(
    city: str, current: dict[str, Any], aq: dict[str, Any] | None
) -> dict[str, Any] | None:
    ts = _parse_ts(current.get("time"))
    if ts is None:
        log.warning("weather: bad current.time %r for %s, skipped", current.get("time"), city)
        return None
    aq = aq or {}
    return {
        "ts": ts,
        "city": city,
        "temp_c": _num(current.get("temperature_2m")),
        "feels_like_c": _num(current.get("apparent_temperature")),
        "humidity": _num(current.get("relative_humidity_2m")),
        "wind_kph": _num(current.get("wind_speed_10m")),
        "wind_dir": _num(current.get("wind_direction_10m")),
        "pressure_hpa": _num(current.get("surface_pressure")),
        "precip_mm": _num(current.get("precipitation")),
        "cloud_pct": _num(current.get("cloud_cover")),
        "weather_code": _int(current.get("weather_code")),
        "uv": _num(current.get("uv_index")),
        "aqi_eu": _num(aq.get("european_aqi")),
        "pm2_5": _num(aq.get("pm2_5")),
        "pm10": _num(aq.get("pm10")),
    }


def _fetch_air_quality(ctx: Ctx, cities: list[dict[str, Any]]) -> list[Any]:
    params = {
        **_location_params(cities),
        "current": AIR_QUALITY_VARS,
        "timezone": "UTC",
    }
    try:
        return _get(ctx, AIR_QUALITY_URL, params)
    except Exception as exc:  # AQ is best-effort enrichment
        log.warning("weather: air-quality request failed, AQI columns left empty: %s", exc)
        return []


def fetch(ctx: Ctx) -> Rows:
    cities = ctx.cities
    if not cities:
        log.warning("weather: no cities configured")
        return []

    forecast = _get(
        ctx,
        FORECAST_URL,
        {
            **_location_params(cities),
            "current": CURRENT_VARS,
            "daily": FORECAST_DAILY_VARS,
            "forecast_days": FORECAST_DAYS,
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        },
    )
    air = _fetch_air_quality(ctx, cities)
    aq_by_city = {
        city["name"]: (item or {}).get("current") for city, item in _zip_cities(cities, air, "aq")
    }

    current_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []

    for city, item in _zip_cities(cities, forecast, "forecast"):
        name = city["name"]
        if item is None:
            log.warning("weather: no forecast entry for %s, skipped", name)
            continue

        current = item.get("current")
        if isinstance(current, dict):
            aq_current = aq_by_city.get(name)
            row = _current_row(name, current, aq_current if isinstance(aq_current, dict) else None)
            if row is not None:
                current_rows.append(row)
        else:
            log.warning("weather: no current block for %s, skipped", name)

        for day, idx, block in _daily_series(item.get("daily"), name, "forecast"):
            forecast_rows.append(
                {
                    "city": name,
                    "day": day,
                    "fetched_at": ctx.now,
                    "tmin_c": _num(_col(block, "temperature_2m_min", idx)),
                    "tmax_c": _num(_col(block, "temperature_2m_max", idx)),
                    "precip_mm": _num(_col(block, "precipitation_sum", idx)),
                    "precip_prob": _num(_col(block, "precipitation_probability_max", idx)),
                    "weather_code": _int(_col(block, "weather_code", idx)),
                }
            )
            if idx < DAILY_FROM_FORECAST_DAYS:
                daily_rows.append(
                    {
                        "day": day,
                        "city": name,
                        "tmin_c": _num(_col(block, "temperature_2m_min", idx)),
                        "tmax_c": _num(_col(block, "temperature_2m_max", idx)),
                        "precip_mm": _num(_col(block, "precipitation_sum", idx)),
                        "wind_max_kph": None,  # not requested from the forecast daily block
                        "weather_code": _int(_col(block, "weather_code", idx)),
                    }
                )

    if not current_rows and not forecast_rows:
        raise ValueError("weather: forecast response contained no usable locations")

    return [
        ("weather_current", current_rows),
        ("weather_forecast", forecast_rows),
        ("weather_daily", daily_rows),
    ]


# --------------------------------------------------------------------------- backfill


def backfill(ctx: Ctx) -> Rows:
    cities = ctx.cities
    if not cities:
        log.warning("weather: no cities configured, nothing to backfill")
        return []

    end = (ctx.now - timedelta(days=ARCHIVE_LAG_DAYS)).date()
    start = (ctx.now - timedelta(days=BACKFILL_DAYS)).date()
    archive = _get(
        ctx,
        ARCHIVE_URL,
        {
            **_location_params(cities),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ARCHIVE_DAILY_VARS,
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        },
    )

    rows: list[dict[str, Any]] = []
    for city, item in _zip_cities(cities, archive, "archive"):
        name = city["name"]
        if item is None:
            log.warning("weather: no archive entry for %s, skipped", name)
            continue
        for day, idx, block in _daily_series(item.get("daily"), name, "archive"):
            rows.append(
                {
                    "day": day,
                    "city": name,
                    "tmin_c": _num(_col(block, "temperature_2m_min", idx)),
                    "tmax_c": _num(_col(block, "temperature_2m_max", idx)),
                    "precip_mm": _num(_col(block, "precipitation_sum", idx)),
                    "wind_max_kph": _num(_col(block, "wind_speed_10m_max", idx)),
                    "weather_code": _int(_col(block, "weather_code", idx)),
                }
            )

    if not rows:
        raise ValueError("weather: archive response contained no usable locations")
    return [("weather_daily", rows)]


SOURCE = Source(
    name="weather",
    interval=900,
    fetch=fetch,
    backfill=backfill,
    tables=["weather_current", "weather_forecast", "weather_daily"],
    description="Open-Meteo current conditions, 7-day forecast, air quality and daily history",
)

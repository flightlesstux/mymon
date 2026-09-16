"""One-off retroactive fill for gaps that predate this collector's first run.

Not wired into the normal ``Source.backfill`` mechanism, which only triggers when a table
is completely empty — these tables already have live data; we're filling a historical
window *behind* it. Run via ``make fill-gaps`` (``fill_gaps.py`` is the entry point).

Each function reuses the parser already written and tested for that source's live fetch —
this module only adds the "walk a historical date range" part.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from .source import Ctx
from .sources import fuel_tr as fuel_tr_source
from .sources import fx as fx_source
from .sources.weather import (
    _as_list,
    _col,
    _int,
    _location_params,
    _num,
    _parse_ts,
    _zip_cities,
)

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- TCMB fx, day by day
#
# today.xml only ever has today's rates, but TCMB archives every past business day's
# bulletin at a predictable URL, so the existing XML parser (parse_tcmb) can be pointed at
# each day in turn.


def tcmb_daily(ctx: Ctx, start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    misses = 0
    day = start
    while day <= end:
        url = f"https://www.tcmb.gov.tr/kurlar/{day:%Y%m}/{day:%d%m%Y}.xml"
        try:
            resp = ctx.http.get(url)
            if resp.status_code == 200:
                rows.extend(fx_source.parse_tcmb(resp.content))
            else:
                misses += 1
        except (httpx.HTTPError, ValueError) as exc:
            misses += 1
            log.debug("tcmb_daily %s: %s", day, exc)
        day += timedelta(days=1)
    log.info("tcmb_daily: %d rows, %d days with no bulletin (weekends/holidays)", len(rows), misses)
    return rows


# --------------------------------------------------------------------- GFZ Potsdam Kp history
#
# NOAA SWPC's Kp file only covers a rolling week; GFZ Potsdam (the index's original source)
# serves any historical range for free. Same row shape as the live source, solar wind/Bz left
# None since GFZ doesn't carry those.

GFZ_KP_URL = "https://kp.gfz-potsdam.de/app/json/"


def kp_history(ctx: Ctx, start: date, end: date) -> list[dict[str, Any]]:
    params = {
        "start": f"{start.isoformat()}T00:00:00Z",
        "end": f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z",
        "index": "Kp",
    }
    resp = ctx.http.get(GFZ_KP_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    kp_values = data.get("Kp") or []
    times = data.get("datetime") or []
    rows: list[dict[str, Any]] = []
    for ts_str, value in zip(times, kp_values, strict=False):
        ts = _parse_ts(str(ts_str))
        if ts is None or value is None:
            continue
        rows.append(
            {"ts": ts, "kp": float(value), "solar_wind_speed": None,
             "solar_wind_density": None, "bz": None}
        )
    return rows


# --------------------------------------------------------------------- weather + air quality
#
# Open-Meteo's archive covers hourly variables (not just the daily min/max the regular
# backfill uses), and its air-quality archive covers the same range, so weather_current's
# columns can be reconstructed hour by hour. Fetched in month-sized chunks so one bad
# request doesn't cost the whole range.

WEATHER_HOURLY_VARS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,"
    "wind_direction_10m,surface_pressure,precipitation,cloud_cover,weather_code,uv_index"
)
AQ_HOURLY_VARS = "european_aqi,pm2_5,pm10"


def _aq(aq_hourly: dict[str, Any] | None, key: str, idx: int | None) -> float | None:
    if aq_hourly is None or idx is None:
        return None
    return _num(_col(aq_hourly, key, idx))


def _month_chunks(start: date, end: date):
    cur = start.replace(day=1)
    while cur <= end:
        nxt = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
        chunk_end = min(nxt - timedelta(days=1), end)
        yield max(cur, start), chunk_end
        cur = nxt


def weather_hourly(ctx: Ctx, start: date, end: date) -> list[dict[str, Any]]:
    cities = ctx.cities
    rows: list[dict[str, Any]] = []
    for chunk_start, chunk_end in _month_chunks(start, end):
        common = {
            **_location_params(cities),
            "start_date": chunk_start.isoformat(),
            "end_date": chunk_end.isoformat(),
            "timezone": "UTC",
        }
        try:
            w_resp = ctx.http.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={**common, "hourly": WEATHER_HOURLY_VARS, "wind_speed_unit": "kmh"},
            )
            w_resp.raise_for_status()
            weather_items = _as_list(w_resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("weather_hourly: %s..%s failed: %s", chunk_start, chunk_end, exc)
            continue

        try:
            aq_resp = ctx.http.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={**common, "hourly": AQ_HOURLY_VARS},
            )
            aq_resp.raise_for_status()
            aq_items = _as_list(aq_resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("weather_hourly AQ: %s..%s failed, AQI left empty: %s",
                        chunk_start, chunk_end, exc)
            aq_items = [None] * len(cities)

        w_paired = _zip_cities(cities, weather_items, "hist-weather")
        aq_paired = _zip_cities(cities, aq_items, "hist-aq")
        for (city, w_item), (_, aq_item) in zip(w_paired, aq_paired, strict=True):
            name = city["name"]
            w_hourly = (w_item or {}).get("hourly") if w_item else None
            if not isinstance(w_hourly, dict) or not isinstance(w_hourly.get("time"), list):
                continue
            aq_hourly = (aq_item or {}).get("hourly") if aq_item else None
            aq_times = aq_hourly.get("time") if isinstance(aq_hourly, dict) else None
            aq_index = {t: i for i, t in enumerate(aq_times)} if aq_times else {}

            for idx, t in enumerate(w_hourly["time"]):
                ts = _parse_ts(t)
                if ts is None:
                    continue
                aq_idx = aq_index.get(t)
                rows.append(
                    {
                        "ts": ts,
                        "city": name,
                        "temp_c": _num(_col(w_hourly, "temperature_2m", idx)),
                        "feels_like_c": _num(_col(w_hourly, "apparent_temperature", idx)),
                        "humidity": _num(_col(w_hourly, "relative_humidity_2m", idx)),
                        "wind_kph": _num(_col(w_hourly, "wind_speed_10m", idx)),
                        "wind_dir": _num(_col(w_hourly, "wind_direction_10m", idx)),
                        "pressure_hpa": _num(_col(w_hourly, "surface_pressure", idx)),
                        "precip_mm": _num(_col(w_hourly, "precipitation", idx)),
                        "cloud_pct": _num(_col(w_hourly, "cloud_cover", idx)),
                        "weather_code": _int(_col(w_hourly, "weather_code", idx)),
                        "uv": _num(_col(w_hourly, "uv_index", idx)),
                        "aqi_eu": _aq(aq_hourly, "european_aqi", aq_idx),
                        "pm2_5": _aq(aq_hourly, "pm2_5", aq_idx),
                        "pm10": _aq(aq_hourly, "pm10", aq_idx),
                    }
                )
        log.info("weather_hourly: %s..%s -> %d rows so far", chunk_start, chunk_end, len(rows))
    return rows


# ---------------------------------------------------------------- Turkey pump prices via Wayback
#
# Petrol Ofisi's page has no history of its own, but the Wayback Machine has crawled it
# periodically; each snapshot is fed to the existing HTML parser unchanged. Sparse (whatever
# the crawler happened to capture) rather than daily — flagged with a distinct `source` so
# it's never confused with the live daily scrape.

WAYBACK_CDX_URL = "http://web.archive.org/cdx/search/cdx"
WAYBACK_SOURCE = "petrolofisi_wayback"


def _wayback_snapshots(ctx: Ctx, page_url: str, start: date, end: date) -> list[str]:
    params = {
        "url": page_url,
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "output": "json",
        "fl": "timestamp,statuscode",
        "collapse": "timestamp:8",  # at most one snapshot per calendar day
    }
    resp = ctx.http.get(WAYBACK_CDX_URL, params=params, timeout=40)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, list) or len(body) <= 1:
        return []
    return [row[0] for row in body[1:] if len(row) >= 2 and row[1] == "200"]


def fuel_tr_wayback(ctx: Ctx, start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for region, (slug, prefer) in fuel_tr_source.PROVINCES.items():
        page_url = fuel_tr_source.BASE_URL.format(slug=slug)
        try:
            snapshots = _wayback_snapshots(ctx, page_url, start, end)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("fuel_tr_wayback: %s snapshot list failed: %s", region, exc)
            continue
        log.info("fuel_tr_wayback: %s has %d snapshots in range", region, len(snapshots))
        for ts in snapshots:
            archived_url = f"http://web.archive.org/web/{ts}id_/{page_url}"
            try:
                resp = ctx.http.get(archived_url, timeout=40)
                resp.raise_for_status()
                prices = fuel_tr_source.parse_page(resp.text, prefer)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("fuel_tr_wayback: %s %s failed: %s", region, ts, exc)
                continue
            try:
                day = datetime.strptime(ts[:8], "%Y%m%d").date()
            except ValueError:
                continue
            for fuel, price in prices.items():
                rows.append(
                    {
                        "period_date": day,
                        "country_iso2": "TR",
                        "region": region,
                        "fuel_type": fuel,
                        "price": price,
                        "currency": "TRY",
                        "unit": "TRY/L",
                        "source": WAYBACK_SOURCE,
                    }
                )
    return rows


__all__ = ["tcmb_daily", "kp_history", "weather_hourly", "fuel_tr_wayback"]

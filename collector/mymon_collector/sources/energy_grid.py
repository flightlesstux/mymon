"""Live electricity grid data — global, not Netherlands-specific.

Two keyless APIs, both confirmed live (2026-09):
- Denmark's Energi Data Service (``api.energidataservice.dk``): hourly production/
  consumption settlement, per price area (DK1 west, DK2 east). Runs a few days behind
  real time (settlement lag), not truly live — the collector just picks up new hours as
  they're published.
- UK's Carbon Intensity API (``api.carbonintensity.org.uk``, National Grid ESO data):
  current + forecast grid carbon intensity for Great Britain, in near-real time.

Both land in ``energy_grid`` (ts, region, indicator, value, unit, source) — a live
snapshot table with a retention policy (see retention.py), not a backfillable archive
like price_index; there's no historical query API worth building against here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "energy_grid"
ENERGI_BASE = "https://api.energidataservice.dk/dataset/ProductionConsumptionSettlement"
CARBON_BASE = "https://api.carbonintensity.org.uk/intensity"
FETCH_LIMIT = 200  # ~100 hours across DK1+DK2 at hourly granularity


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _row(
    ts: datetime, region: str, indicator: str, value: float, unit: str, source: str
) -> dict[str, Any]:
    return {"ts": ts, "region": region, "indicator": indicator, "value": value,
            "unit": unit, "source": source}


# --------------------------------------------------------------------------- Denmark grid


def _dk_rows(ctx: Ctx) -> list[dict[str, Any]]:
    resp = ctx.http.get(ENERGI_BASE, params={"limit": FETCH_LIMIT, "sort": "HourUTC desc"})
    resp.raise_for_status()
    records = resp.json().get("records", [])
    rows: list[dict[str, Any]] = []
    for rec in records:
        raw_ts = rec.get("HourUTC")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts).replace(tzinfo=None)
        except ValueError:
            continue
        region = rec.get("PriceArea")
        if not region:
            continue

        wind = sum(_num(rec.get(k)) or 0 for k in (
            "OffshoreWindLt100MW_MWh", "OffshoreWindGe100MW_MWh",
            "OnshoreWindLt50kW_MWh", "OnshoreWindGe50kW_MWh",
        ))
        rows.append(_row(ts, region, "wind_generation_mwh", wind, "MWh", "energidataservice"))

        solar = sum(_num(rec.get(k)) or 0 for k in (
            "SolarPowerLt10kW_MWh", "SolarPowerGe10Lt40kW_MWh",
            "SolarPowerGe40kW_MWh", "SolarPowerSelfConMWh",
        ))
        rows.append(_row(ts, region, "solar_generation_mwh", solar, "MWh", "energidataservice"))

        central = _num(rec.get("CentralPowerMWh"))
        if central is not None:
            rows.append(_row(ts, region, "central_power_mwh", central, "MWh", "energidataservice"))

        consumption = _num(rec.get("GrossConsumptionMWh"))
        if consumption is not None:
            rows.append(_row(ts, region, "gross_consumption_mwh", consumption, "MWh",
                              "energidataservice"))
    return rows


# --------------------------------------------------------------------------- UK grid


def _uk_rows(ctx: Ctx) -> list[dict[str, Any]]:
    resp = ctx.http.get(CARBON_BASE)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    rows: list[dict[str, Any]] = []
    for rec in data:
        raw_ts = rec.get("from")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        intensity = rec.get("intensity", {})
        actual = _num(intensity.get("actual"))
        if actual is not None:
            rows.append(_row(ts, "GB", "carbon_intensity_gco2_kwh", actual, "gCO2/kWh",
                              "carbonintensity.org.uk"))
        forecast = _num(intensity.get("forecast"))
        if forecast is not None:
            rows.append(_row(ts, "GB", "carbon_intensity_forecast_gco2_kwh", forecast,
                              "gCO2/kWh", "carbonintensity.org.uk"))
    return rows


# --------------------------------------------------------------------------- source


def _run_upstreams(
    ctx: Ctx, upstreams: tuple[tuple[str, Any], ...]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    failures = 0
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - one upstream must not sink the others
            log.warning("energy_grid: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("energy_grid: %s returned no rows", name)
            failures += 1
            continue
        log.info("energy_grid: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (("denmark", _dk_rows), ("uk", _uk_rows)))
    if not rows:
        raise RuntimeError("energy_grid: every upstream failed")
    log.info("energy_grid: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, rows)]


SOURCE = Source(
    name="energy_grid",
    interval=1800,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Live electricity grid data: Denmark's wind/solar/conventional generation mix "
        "and consumption per price area (Energi Data Service), and Great Britain's "
        "grid carbon intensity, actual + forecast (National Grid ESO)."
    ),
)

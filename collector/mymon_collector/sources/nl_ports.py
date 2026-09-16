"""Netherlands ports & shipping: CBS StatLine, same OData v3 mechanism as nl_metrics.py.

Cargo tonnage and ship counts are per-port (``85598NED``, ``85602NED``), landing in
``port_metric`` (mirrors ``region_metric``, keyed by CBS's NederlandseZeehavens codes —
see the ``port`` table seeded in the schema). Container throughput (``85601NED``) has no
port dimension in this table — it's national-only — so it lands in ``price_index`` instead,
alongside the freight-by-mode split (``83101NED``).

Every table is small; each run re-pulls full history, no separate backfill.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "price_index"
PORT_TABLE = "port_metric"
COUNTRY = "NLD"
CBS_BASE = "https://opendata.cbs.nl/ODataApi/odata"

# CBS NederlandseZeehavens codes (85598NED, 85602NED) -> our port.code
PORTS: dict[str, str] = {
    "A041797": "A041797",  # Rotterdam
    "A041794": "A041794",  # Amsterdam
    "A041795": "A041795",  # Groningen Seaports
    "A041798": "A041798",  # Zeeland Seaports
}


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _row(period: date, indicator: str, value: float, unit: str, source: str) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": COUNTRY,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": source,
    }


def _port_row(
    period: date, port_code: str, indicator: str, value: float, unit: str
) -> dict[str, Any]:
    return {
        "period_date": period,
        "port_code": port_code,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "cbs",
    }


def _cbs_period(value: str) -> date | None:
    """CBS months look like ``2025MM01``, quarters ``2025KW02``, years ``2025JJ00``."""
    s = (value or "").strip()
    if len(s) != 8:
        return None
    if s[4:6] == "KW":
        try:
            year, q = int(s[:4]), int(s[6:8])
        except ValueError:
            return None
        if q not in (1, 2, 3, 4):
            return None
        return date(year, (q - 1) * 3 + 1, 1)
    try:
        year = int(s[:4])
    except ValueError:
        return None
    if s[4:6] == "MM":
        try:
            return date(year, int(s[6:8]), 1)
        except ValueError:
            return None
    if s[4:6] == "JJ":
        return date(year, 1, 1)
    return None


def _cbs_get(ctx: Ctx, table: str, filt: str | None = None) -> list[dict[str, Any]]:
    url = f"{CBS_BASE}/{table}/TypedDataSet"
    params = {"$format": "json"}
    if filt:
        params["$filter"] = filt
    resp = ctx.http.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    value = data.get("value")
    if not isinstance(value, list):
        raise ValueError(f"CBS {table}: unexpected payload shape")
    return value


# --------------------------------------------------------------------------- CBS: cargo by port
#
# 85598NED — quarterly cargo tonnage, per port, split by flow (in/out) and cargo type.
# Totaal aan- en afvoer (A045946) x Totaal lading (T001292) gives one clean per-port
# tonnage series.

def _port_cargo_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for port_code in PORTS:
        filt = (
            f"NederlandseZeehavens eq '{port_code}' "
            f"and Vervoerstroom eq 'A045946' and SoortLading eq 'T001292'"
        )
        for rec in _cbs_get(ctx, "85598NED", filt):
            period = _cbs_period(rec.get("Perioden"))
            if period is None:
                continue
            tonnes = _num(rec.get("BrutoplusgewichtOvergeslagenGoederen_1"))
            if tonnes is not None:
                rows.append(_port_row(period, port_code, "cargo_1000t", tonnes, "1000 tonnes"))
    return rows


# --------------------------------------------------------------------------- CBS: ships by port
#
# 85602NED — annual number of seagoing ship calls, per port, all ship types (T001663).

def _port_ship_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for port_code in PORTS:
        filt = f"NederlandseZeehavens eq '{port_code}' and TypeZeeschip eq 'T001663'"
        for rec in _cbs_get(ctx, "85602NED", filt):
            period = _cbs_period(rec.get("Perioden"))
            if period is None:
                continue
            ships = _num(rec.get("Zeeschepen_1"))
            if ships is not None:
                rows.append(_port_row(period, port_code, "ship_calls", ships, "count"))
    return rows


# ------------------------------------------------------------------- CBS: containers, national
#
# 85601NED — quarterly container throughput, national only (no port dimension). Totaal
# aan- en afvoer (A045946) x Totaal overgeslagen containers (T001664).

def _container_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    filt = "Vervoerstroom eq 'A045946' and ContainerGrootte eq 'T001664'"
    for rec in _cbs_get(ctx, "85601NED", filt):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        teu = _num(rec.get("OvergeslagenContainers_1"))
        if teu is not None:
            rows.append(_row(period, "containers_1000teu", teu, "1000 TEU", "cbs"))
        tonnes = _num(rec.get("BrutoplusgewichtOvergeslagenContainers_2"))
        if tonnes is not None:
            rows.append(_row(period, "container_cargo_1000t", tonnes, "1000 tonnes", "cbs"))
    return rows


# --------------------------------------------------------------------------- CBS: freight by mode
#
# 83101NED — annual freight transport to/from NL by mode of transport.

FREIGHT_MODES: dict[str, str] = {
    "A043078": "sea",
    "A043079": "inland_waterway",
    "A043080": "road",
    "A043081": "rail",
    "A043082": "air",
    "A043083": "pipeline",
}


def _freight_mode_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _cbs_get(ctx, "83101NED"):
        period = _cbs_period(rec.get("Perioden"))
        if period is None:
            continue
        mode_code = rec.get("Vervoerwijzen")
        name = FREIGHT_MODES.get(mode_code)
        if name is None:
            continue
        total = _num(rec.get("TotaalGoederenvervoer_1"))
        if total is not None:
            rows.append(_row(period, f"freight_total_mt_{name}", total, "million tonnes", "cbs"))
        imports = _num(rec.get("AanvoerNaarNederland_4"))
        if imports is not None:
            rows.append(_row(period, f"freight_import_mt_{name}", imports, "million tonnes", "cbs"))
        exports = _num(rec.get("AfvoerNaarBuitenland_5"))
        if exports is not None:
            rows.append(_row(period, f"freight_export_mt_{name}", exports, "million tonnes", "cbs"))
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
            log.warning("nl_ports: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("nl_ports: %s returned no rows", name)
            failures += 1
            continue
        log.info("nl_ports: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def _dedupe(rows: list[dict[str, Any]], key_field: str) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        seen[(r["period_date"], r[key_field], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    country_rows, country_failures = _run_upstreams(ctx, (
        ("containers", _container_rows),
        ("freight_modes", _freight_mode_rows),
    ))
    port_rows, port_failures = _run_upstreams(ctx, (
        ("port_cargo", _port_cargo_rows),
        ("port_ships", _port_ship_rows),
    ))
    if not country_rows and not port_rows:
        raise RuntimeError("nl_ports: every upstream failed")
    log.info("nl_ports: %d country rows (%d failures), %d port rows (%d failures)",
              len(country_rows), country_failures, len(port_rows), port_failures)
    return [
        (TABLE, _dedupe(country_rows, "country_iso3")),
        (PORT_TABLE, _dedupe(port_rows, "port_code")),
    ]


SOURCE = Source(
    name="nl_ports",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE, PORT_TABLE],
    description=(
        "Netherlands seaports and freight: CBS cargo tonnage and ship calls per port "
        "(Rotterdam, Amsterdam, Groningen Seaports, Zeeland Seaports), national "
        "container throughput, and freight transport by mode (road/rail/water/etc.)."
    ),
)

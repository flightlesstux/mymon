"""Germany, Italy, Spain, Greece and Turkey: Eurostat's dissemination API, one shared
module for all five since Eurostat's ``geo`` dimension accepts a list — one HTTP request
per indicator covers every country at once, rather than five near-identical national
statistics office integrations (Destatis, ISTAT, INE, ELSTAT, TÜİK all have different
APIs; Eurostat harmonizes across all of them, Turkey included as a candidate country with
partial-but-real coverage, confirmed live).

Eurostat's JSON-stat response packs every dimension combination into one flat ``value``
dict keyed by a computed linear index (``_decode`` below implements the standard
JSON-stat v1.1 index formula: for dimensions in ``id`` order with sizes in ``size``,
flat_index = sum(dim_index * product of all later dims' sizes)). Any country missing
from a given dataset (not every indicator is TR-published) simply doesn't appear in that
dimension's category list — no special-casing needed, the decoder only ever emits rows
for geo/time combinations Eurostat actually returned.

Everything lands in ``price_index`` (the existing generic table already keyed by
``country_iso3`` — no new schema needed) except population/births/deaths/migration,
which land in the same table too (unlike the NL region-level split, there's no
sub-national breakdown here). No separate backfill: every dataset call returns full
history for the requested ``sinceTimePeriod`` onward, and the datasets are small enough
that a full daily re-pull is cheap.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

TABLE = "price_index"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
SINCE = "2000"

GEO_TO_ISO3: dict[str, str] = {
    "DE": "DEU", "IT": "ITA", "ES": "ESP", "EL": "GRC", "TR": "TUR",
}
GEOS = list(GEO_TO_ISO3)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _row(
    period: date, country_iso3: str, indicator: str, value: float, unit: str
) -> dict[str, Any]:
    return {
        "period_date": period,
        "country_iso3": country_iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": "eurostat",
    }


def _period_from_time_code(code: str) -> date | None:
    """Eurostat time codes: ``2026-01`` (monthly), ``2026-Q1`` (quarterly), ``2026`` (annual)."""
    code = (code or "").strip()
    if len(code) == 4 and code.isdigit():
        return date(int(code), 1, 1)
    if len(code) == 7 and code[4] == "-" and code[5] == "Q":
        try:
            year, q = int(code[:4]), int(code[6])
        except ValueError:
            return None
        if q not in (1, 2, 3, 4):
            return None
        return date(year, (q - 1) * 3 + 1, 1)
    if len(code) == 7 and code[4] == "-":
        try:
            return date(int(code[:4]), int(code[5:7]), 1)
        except ValueError:
            return None
    return None


def _decode(data: dict[str, Any]) -> list[tuple[dict[str, str], float]]:
    """JSON-stat v1.1 -> ``[(dims, value), ...]``, one entry per non-null observation.

    Defensive against a query that matched nothing (Eurostat can return a
    dimension-metadata-free stub in that case) — treated as "no data", not an error.
    """
    dim_ids: list[str] = data.get("id", [])
    sizes: list[int] = data.get("size", [])
    if not dim_ids or len(dim_ids) != len(sizes):
        return []

    # index (within its dimension) -> code, per dimension, in the order codes were
    # assigned (Eurostat's "index" map already gives code -> position)
    categories: list[list[str]] = []
    for dim_id in dim_ids:
        idx_map = data.get("dimension", {}).get(dim_id, {}).get("category", {}).get("index")
        if not idx_map:
            return []
        ordered = sorted(idx_map.items(), key=lambda kv: kv[1])
        categories.append([code for code, _ in ordered])

    strides = [1] * len(dim_ids)
    for i in range(len(dim_ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    raw_values: dict[str, Any] = data.get("value", {})
    out: list[tuple[dict[str, str], float]] = []
    for flat_key, raw in raw_values.items():
        value = _num(raw)
        if value is None:
            continue
        flat_index = int(flat_key)
        dims: dict[str, str] = {}
        remainder = flat_index
        for dim_id, stride, cats in zip(dim_ids, strides, categories, strict=True):
            pos, remainder = divmod(remainder, stride) if stride else (0, remainder)
            if pos >= len(cats):
                dims = {}
                break
            dims[dim_id] = cats[pos]
        if dims:
            out.append((dims, value))
    return out


def _eurostat_get(
    ctx: Ctx, dataset: str, params: dict[str, Any]
) -> list[tuple[dict[str, str], float]]:
    query = {"format": "JSON", "lang": "en", "geo": GEOS, **params}
    resp = ctx.http.get(f"{BASE}/{dataset}", params=query)
    resp.raise_for_status()
    return _decode(resp.json())


# --------------------------------------------------------------------------- CPI
#
# Four independent HTTP calls (index + YoY, headline + food) — each its own top-level
# upstream (see fetch()) rather than one function making all four, so a failure in any
# one doesn't discard the others' already-fetched rows.


def _single_series_rows(
    ctx: Ctx, dataset: str, params: dict[str, Any], indicator: str, unit: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dims, value in _eurostat_get(ctx, dataset, {**params, "sinceTimePeriod": SINCE}):
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if iso3 is None or period is None:
            continue
        rows.append(_row(period, iso3, indicator, value, unit))
    return rows


def _cpi_index_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "prc_hicp_midx", {"coicop": "CP00", "unit": "I15"}, "cpi_index", "2015=100")


def _cpi_inflation_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "prc_hicp_manr", {"coicop": "CP00"}, "cpi_inflation_pct", "%")


def _food_cpi_index_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "prc_hicp_midx", {"coicop": "CP01", "unit": "I15"}, "food_cpi_index", "2015=100")


def _food_cpi_inflation_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "prc_hicp_manr", {"coicop": "CP01"}, "food_cpi_inflation_pct", "%")


# --------------------------------------------------------------------------- unemployment


def _unemployment_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "une_rt_m", {"sex": "T", "age": "TOTAL", "unit": "PC_ACT", "s_adj": "SA"},
        "unemployment_rate_pct", "%")


# --------------------------------------------------------------------------- population


def _population_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "demo_pjan", {"sex": "T", "age": "TOTAL"}, "population_total", "count")


# ----------------------------------------------------------------- births/deaths/migration

DEMO_INDICATORS: dict[str, tuple[str, str]] = {
    "LBIRTH": ("births", "count"),
    "DEATH": ("deaths", "count"),
    "CNMIGRAT": ("net_migration", "count"),
    "GROW": ("population_growth", "count"),
}


def _demographics_rows(ctx: Ctx) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dims, value in _eurostat_get(ctx, "demo_gind", {"sinceTimePeriod": SINCE}):
        spec = DEMO_INDICATORS.get(dims.get("indic_de", ""))
        iso3 = GEO_TO_ISO3.get(dims.get("geo", ""))
        period = _period_from_time_code(dims.get("time", ""))
        if spec is None or iso3 is None or period is None:
            continue
        indicator, unit = spec
        rows.append(_row(period, iso3, indicator, value, unit))
    return rows


# --------------------------------------------------------------------------- house prices


def _house_price_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "prc_hpi_q", {"purchase": "TOTAL", "unit": "I15_Q"},
        "house_price_index", "2015=100")


# --------------------------------------------------------------------- confidence indices


def _consumer_confidence_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "ei_bsco_m", {"indic": "BS-CSMCI"}, "consumer_confidence_index", "index")


def _producer_confidence_rows(ctx: Ctx) -> list[dict[str, Any]]:
    return _single_series_rows(
        ctx, "ei_bsin_m_r2", {"indic": "BS-ICI"}, "producer_confidence_index", "index")


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
            log.warning("eurostat_metrics: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("eurostat_metrics: %s returned no rows", name)
            failures += 1
            continue
        log.info("eurostat_metrics: %s -> %d rows", name, len(part))
        rows.extend(part)
    return rows, failures


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        seen[(r["period_date"], r["country_iso3"], r["indicator"], r["source"])] = r
    return list(seen.values())


def fetch(ctx: Ctx) -> Rows:
    rows, failures = _run_upstreams(ctx, (
        ("cpi_index", _cpi_index_rows),
        ("cpi_inflation", _cpi_inflation_rows),
        ("food_cpi_index", _food_cpi_index_rows),
        ("food_cpi_inflation", _food_cpi_inflation_rows),
        ("unemployment", _unemployment_rows),
        ("population", _population_rows),
        ("demographics", _demographics_rows),
        ("house_prices", _house_price_rows),
        ("consumer_confidence", _consumer_confidence_rows),
        ("producer_confidence", _producer_confidence_rows),
    ))
    if not rows:
        raise RuntimeError("eurostat_metrics: every upstream failed")
    log.info("eurostat_metrics: %d rows (%d upstream failures)", len(rows), failures)
    return [(TABLE, _dedupe(rows))]


SOURCE = Source(
    name="eurostat_metrics",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description=(
        "Germany, Italy, Spain, Greece and Turkey via Eurostat: CPI/food CPI (index + "
        "YoY), unemployment, population, births/deaths/migration, house price index, "
        "consumer and producer confidence — since 2000 where each series goes back "
        "that far."
    ),
)

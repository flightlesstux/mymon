"""Eurostat household electricity and gas prices (semi-annual, EUR/kWh, all taxes included).

Datasets ``nrg_pc_204`` (electricity, consumption band DC = 2 500-4 999 kWh/year, code
``KWH2500-4999``) and ``nrg_pc_202`` (gas, band D2 = 20-199 GJ/year, code ``GJ20-199``), queried
through the JSON-stat dissemination API. Band codes were verified live: the API exposes the
``nrg_cons`` dimension with ``KWH*``/``GJ*`` codes (the legacy numeric ``consom`` codes are gone).

JSON-stat packs the cube into ``value`` keyed by a flat row-major index; :func:`jsonstat_rows`
decodes it using ``id`` (dimension order), ``size`` and each dimension's ``category.index``.
Eurostat geo codes are 2-letter with its own quirks (``EL`` Greece, ``UK``) and are mapped to
ISO3 here; ``EU27_2020`` becomes ``EUU`` and ``EA`` (euro area) becomes ``EMU``. Unknown geos
are skipped. Semester codes ``2024-S1``/``2024-S2`` map to 1 January / 1 July.

Full history (from 2007) is ~1.5k values per dataset, so every run re-pulls everything and no
backfill is needed. Rows go to ``price_index`` with ``source='eurostat'``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
COMMON_PARAMS = {"format": "JSON", "lang": "EN", "unit": "KWH", "currency": "EUR", "tax": "I_TAX"}
DATASETS: dict[str, tuple[str, dict[str, str]]] = {
    # dataset -> (indicator, extra query params)
    "nrg_pc_204": ("electricity_household_eur_kwh", {"nrg_cons": "KWH2500-4999"}),
    "nrg_pc_202": ("gas_household_eur_kwh", {"nrg_cons": "GJ20-199"}),
}
UNIT = "EUR/kWh"
SOURCE_NAME = "eurostat"
TABLE = "price_index"

GEO_TO_ISO3: dict[str, str] = {
    "EU27_2020": "EUU", "EU28": "EUU", "EU": "EUU", "EA": "EMU", "EA19": "EMU", "EA20": "EMU",
    "AL": "ALB", "AT": "AUT", "BA": "BIH", "BE": "BEL", "BG": "BGR", "CH": "CHE", "CY": "CYP",
    "CZ": "CZE", "DE": "DEU", "DK": "DNK", "EE": "EST", "EL": "GRC", "ES": "ESP", "FI": "FIN",
    "FR": "FRA", "GE": "GEO", "HR": "HRV", "HU": "HUN", "IE": "IRL", "IS": "ISL", "IT": "ITA",
    "LI": "LIE", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MD": "MDA", "ME": "MNE", "MK": "MKD",
    "MT": "MLT", "NL": "NLD", "NO": "NOR", "PL": "POL", "PT": "PRT", "RO": "ROU", "RS": "SRB",
    "SE": "SWE", "SI": "SVN", "SK": "SVK", "TR": "TUR", "UA": "UKR", "UK": "GBR", "XK": "XKX",
}  # fmt: skip

_TIME_RE = re.compile(r"^(\d{4})(?:-?([SQM])(\d{1,2}))?(?:-(\d{2}))?$")


# --------------------------------------------------------------------------- JSON-stat


def jsonstat_rows(payload: dict[str, Any]) -> Iterator[tuple[dict[str, str], Any]]:
    """Yield ``({dimension: code, ...}, value)`` for every populated cell of a JSON-stat dataset.

    ``value`` may be a dict of flat index -> value (sparse) or a dense list; ``category.index``
    may be a dict code -> position or a list of codes. Cells whose value is ``None`` are skipped.
    """
    ids = payload.get("id")
    size = payload.get("size")
    dims = payload.get("dimension")
    if not isinstance(ids, list) or not isinstance(size, list) or not isinstance(dims, dict):
        raise ValueError("not a JSON-stat dataset (missing id/size/dimension)")
    if len(ids) != len(size):
        raise ValueError("JSON-stat id/size length mismatch")

    codes: list[list[str | None]] = []
    for name, n in zip(ids, size, strict=True):
        index = (dims.get(name) or {}).get("category", {}).get("index")
        if isinstance(index, dict):
            by_pos: list[str | None] = [None] * int(n)
            for code, pos in index.items():
                if isinstance(pos, int) and 0 <= pos < n:
                    by_pos[pos] = str(code)
        elif isinstance(index, list):
            by_pos = [str(c) for c in index[:n]] + [None] * max(0, n - len(index))
        elif n == 1:
            # single-category dimension may carry only a label
            label = (dims.get(name) or {}).get("category", {}).get("label", {})
            by_pos = [next(iter(label), None)] if isinstance(label, dict) else [None]
        else:
            raise ValueError(f"JSON-stat dimension {name!r} has no category index")
        codes.append(by_pos)

    values = payload.get("value")
    if isinstance(values, dict):
        items = ((int(k), v) for k, v in values.items())
    elif isinstance(values, list):
        items = enumerate(values)
    else:
        raise ValueError("JSON-stat value block missing")

    for flat, value in items:
        if value is None:
            continue
        rem = flat
        positions = [0] * len(size)
        for i in range(len(size) - 1, -1, -1):
            n = int(size[i])
            positions[i] = rem % n
            rem //= n
        if rem:
            log.warning("energy_prices_eu: flat index %d out of range, skipped", flat)
            continue
        yield {ids[i]: codes[i][positions[i]] for i in range(len(ids))}, value


# --------------------------------------------------------------------------- helpers


def _period(code: str | None) -> date | None:
    """``2024-S1`` -> 2024-01-01, ``2024-S2`` -> 2024-07-01; also plain years and ``YYYY-MM``."""
    if not code:
        return None
    m = _TIME_RE.match(code.strip())
    if not m:
        return None
    year = int(m.group(1))
    kind, num, month = m.group(2), m.group(3), m.group(4)
    try:
        if kind == "S":
            return date(year, 1 if int(num) == 1 else 7, 1)
        if kind == "Q":
            return date(year, (int(num) - 1) * 3 + 1, 1)
        if kind == "M":
            return date(year, int(num), 1)
        if month:
            return date(year, int(month), 1)
        return date(year, 1, 1)
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _dataset_rows(payload: dict[str, Any], indicator: str) -> list[dict]:
    rows: list[dict] = []
    unknown_geo: set[str] = set()
    bad_time: set[str] = set()
    nonpositive = 0
    for dims, raw in jsonstat_rows(payload):
        geo = dims.get("geo") or ""
        iso3 = GEO_TO_ISO3.get(geo)
        if iso3 is None:
            unknown_geo.add(geo)
            continue
        period = _period(dims.get("time"))
        if period is None:
            bad_time.add(str(dims.get("time")))
            continue
        value = _num(raw)
        if value is None or value <= 0:
            nonpositive += 1
            continue
        rows.append(
            {
                "period_date": period,
                "country_iso3": iso3,
                "indicator": indicator,
                "value": value,
                "unit": UNIT,
                "source": SOURCE_NAME,
            }
        )
    if unknown_geo:
        log.warning(
            "energy_prices_eu: %s unknown geo codes skipped: %s", indicator, sorted(unknown_geo)
        )
    if bad_time:
        log.warning("energy_prices_eu: %s bad time codes skipped: %s", indicator, sorted(bad_time))
    if nonpositive:
        log.warning(
            "energy_prices_eu: %s skipped %d empty/non-positive prices", indicator, nonpositive
        )
    return rows


# --------------------------------------------------------------------------- source


def fetch(ctx: Ctx) -> Rows:
    rows: list[dict] = []
    failures = 0
    for dataset, (indicator, extra) in DATASETS.items():
        try:
            resp = ctx.http.get(BASE_URL + dataset, params={**COMMON_PARAMS, **extra})
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError("payload is not an object")
            if "error" in payload and "value" not in payload:
                raise ValueError(f"Eurostat error: {payload['error']}")
            part = _dataset_rows(payload, indicator)
        except Exception as exc:  # noqa: BLE001 - one dataset must not sink the other
            log.warning("energy_prices_eu: %s failed: %s", dataset, exc)
            failures += 1
            continue
        log.info("energy_prices_eu: %s -> %d rows", dataset, len(part))
        rows.extend(part)
    if not rows:
        raise RuntimeError("energy_prices_eu: no rows from any dataset")
    return [(TABLE, rows)]


SOURCE = Source(
    name="energy_prices_eu",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description="Eurostat household electricity and gas prices (EUR/kWh incl. taxes, semi-annual)",
)

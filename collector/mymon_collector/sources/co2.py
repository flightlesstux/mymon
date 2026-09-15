"""Mauna Loa monthly mean CO2 (NOAA GML).

``co2_mm_mlo.csv``: ``#`` comment lines, then a header
``year,month,decimal date,average,deseasonalized,ndays,sdev,unc`` and one row per month.
``month`` = date(year, month, 1), ``ppm`` = average, ``trend_ppm`` = deseasonalized.
NOAA marks missing values with ``-99.99`` (older files use ``-9.99``); those become None.
The whole file is fetched on every run (it is ~30 KB), so no backfill is needed.
"""

from __future__ import annotations

import csv
import logging
from datetime import date
from io import StringIO
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv"
_SENTINELS = {-99.99, -9.99}


def _ppm(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return None if num in _SENTINELS or num < 0 else num


def parse_csv(text: str) -> list[dict[str, Any]]:
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise ValueError("co2_mm_mlo.csv has no data lines")
    reader = csv.DictReader(StringIO("\n".join(lines)), skipinitialspace=True)
    fields = [f.strip() for f in reader.fieldnames or []]
    if "year" not in fields or "month" not in fields or "average" not in fields:
        raise ValueError(f"co2_mm_mlo.csv header unexpected: {reader.fieldnames!r}")
    rows: list[dict[str, Any]] = []
    for rec in reader:
        rec = {(k or "").strip(): (v or "").strip() for k, v in rec.items()}
        try:
            month = date(int(rec["year"]), int(rec["month"]), 1)
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("skipping co2 row %r: %s", rec, exc)
            continue
        rows.append(
            {
                "month": month,
                "ppm": _ppm(rec.get("average")),
                "trend_ppm": _ppm(rec.get("deseasonalized")),
            }
        )
    return rows


def fetch(ctx: Ctx) -> Rows:
    resp = ctx.http.get(URL)
    resp.raise_for_status()
    return [("co2_monthly", parse_csv(resp.text))]


SOURCE = Source(
    name="co2",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=["co2_monthly"],
    description="Mauna Loa monthly mean atmospheric CO2 (NOAA GML)",
)

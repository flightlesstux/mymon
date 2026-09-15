"""BIS central bank policy rates (dataset ``WS_CBPOL``), monthly, ~49 economies.

Endpoint (SDMX 2.1 REST, verified live)::

    https://stats.bis.org/api/v1/data/WS_CBPOL/M..?format=csv&lastNObservations=240&detail=dataonly

``detail=dataonly`` trims the CSV to ``FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE`` (a few KB instead
of ~5 MB with the full attribute columns); the parser reads by header name so both layouts
work. The v2 URL (``/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M..``) answers 404 / 400 and is not
used.

``REF_AREA`` is iso2 (``XM`` = euro area) and is mapped to iso3 through :data:`ISO2_TO_ISO3`;
unknown areas are skipped with one warning each. ``TIME_PERIOD`` is ``YYYY-MM`` and lands on the
first of the month. Some series are discontinued (euro-area members stop in 1998) and simply
carry old periods. Rows: ``price_index`` indicator ``policy_rate_pct``, unit ``%``, source
``bis``. 240 observations x 49 areas is ~12k rows, refreshed whole on every daily run.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

DATA_URL = "https://stats.bis.org/api/v1/data/WS_CBPOL/M.."
LAST_N_OBSERVATIONS = 240
SOURCE_NAME = "bis"
INDICATOR = "policy_rate_pct"
UNIT = "%"

ISO2_TO_ISO3: dict[str, str] = {
    "AR": "ARG", "AT": "AUT", "AU": "AUS", "BE": "BEL", "BR": "BRA", "CA": "CAN", "CH": "CHE",
    "CL": "CHL", "CN": "CHN", "CO": "COL", "CZ": "CZE", "DE": "DEU", "DK": "DNK", "ES": "ESP",
    "FI": "FIN", "FR": "FRA", "GB": "GBR", "GR": "GRC", "HK": "HKG", "HR": "HRV", "HU": "HUN",
    "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IS": "ISL", "IT": "ITA", "JP": "JPN",
    "KR": "KOR", "KW": "KWT", "LU": "LUX", "MA": "MAR", "MK": "MKD", "MX": "MEX", "MY": "MYS",
    "NL": "NLD", "NO": "NOR", "NZ": "NZL", "PE": "PER", "PH": "PHL", "PL": "POL", "PT": "PRT",
    "RO": "ROU", "RS": "SRB", "RU": "RUS", "SA": "SAU", "SE": "SWE", "SG": "SGP", "TH": "THA",
    "TR": "TUR", "US": "USA", "XM": "EMU", "ZA": "ZAF",
}

_PERIOD = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?")  # 2026-08 | 2026-08-15 | 2026


# --------------------------------------------------------------------------- helpers


def _parse_period(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    m = _PERIOD.match(value.strip())
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2] or 1), 1)
    except ValueError:
        return None


def _parse_value(value: Any) -> Decimal | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _rows_from_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    fields = set(reader.fieldnames or [])
    if not {"REF_AREA", "TIME_PERIOD", "OBS_VALUE"} <= fields:
        raise ValueError(f"bis: unexpected CSV header {sorted(fields)}")

    rows: list[dict[str, Any]] = []
    unknown_areas: set[str] = set()
    for rec in reader:
        area = (rec.get("REF_AREA") or "").strip().upper()
        iso3 = ISO2_TO_ISO3.get(area)
        if iso3 is None:
            if area not in unknown_areas:
                unknown_areas.add(area)
                log.warning("bis: unknown REF_AREA %r skipped", area)
            continue
        period = _parse_period(rec.get("TIME_PERIOD"))
        if period is None:
            log.warning("bis: %s: bad TIME_PERIOD %r skipped", area, rec.get("TIME_PERIOD"))
            continue
        value = _parse_value(rec.get("OBS_VALUE"))
        if value is None:
            continue  # unpublished / missing observation
        rows.append(
            {
                "period_date": period,
                "country_iso3": iso3,
                "indicator": INDICATOR,
                "value": value,
                "unit": UNIT,
                "source": SOURCE_NAME,
            }
        )
    return rows


# --------------------------------------------------------------------------- fetch


def fetch(ctx: Ctx) -> Rows:
    resp = ctx.http.get(
        DATA_URL,
        params={
            "format": "csv",
            "lastNObservations": LAST_N_OBSERVATIONS,
            "detail": "dataonly",
        },
        headers={"Accept": "text/csv"},
    )
    resp.raise_for_status()
    rows = _rows_from_csv(resp.text)
    if not rows:
        raise ValueError("bis: CSV contained no usable observations")
    log.info("bis: %d policy-rate rows", len(rows))
    return [("price_index", rows)]


SOURCE = Source(
    name="bis_policy_rates",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=["price_index"],
    description="BIS WS_CBPOL monthly central bank policy rates (~49 economies)",
)

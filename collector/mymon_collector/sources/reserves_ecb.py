"""Euro area (Eurosystem) official reserve assets from the ECB Data Portal.

Probe notes (2026-09): the ``RA`` dataflow ("International Reserves of the Eurosystem",
key ``RA.M.U2.N.8.802.N.A1.E``) is frozen -- every series ends at 2014-08. The BPM6
successor is dataflow ``BPS``. Its monthly euro area series only carry transactions and
other changes (FLOW_STOCK_ENTRY = T / K7A / K7B / KA); the stock (LE) of reserve assets
is published quarterly. No USD-denominated key exists (UNIT_MEASURE is EUR only), so the
value is stored in EUR and tagged ``source = ecb_eur``; dashboards convert.

Series used: ``BPS.Q.N.I10.W1.S121.S1.LE.A.FA.R.F._Z.EUR.X1._X.N.ALL`` (euro area, fixed
composition, reserve assets, closing position, EUR millions, 1999-Q1 onwards, ~110 obs).
Values are multiplied by 10**UNIT_MULT so ``value_usd`` holds whole euros, matching the
World Bank scale. ``period_date`` is the last day of the quarter.
"""

from __future__ import annotations

import calendar
import csv
import io
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

SERIES_KEY = "Q.N.I10.W1.S121.S1.LE.A.FA.R.F._Z.EUR.X1._X.N.ALL"
DATA_URL = f"https://data-api.ecb.europa.eu/service/data/BPS/{SERIES_KEY}"
PARAMS = {"format": "csvdata"}

COUNTRY_ISO3 = "EMU"
COUNTRY = "Euro area"
METRIC = "total"
SOURCE_NAME = "ecb_eur"

_QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR = re.compile(r"^(\d{4})$")


def period_end(text: str) -> date:
    """Map an SDMX TIME_PERIOD (``2026-Q1``, ``2026-03``, ``2026``) to its last day."""
    text = text.strip()
    if m := _QUARTER.match(text):
        year, q = int(m.group(1)), int(m.group(2))
        month = q * 3
    elif m := _MONTH.match(text):
        year, month = int(m.group(1)), int(m.group(2))
    elif m := _YEAR.match(text):
        year, month = int(m.group(1)), 12
    else:
        raise ValueError(f"unsupported TIME_PERIOD {text!r}")
    return date(year, month, calendar.monthrange(year, month)[1])


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "TIME_PERIOD" not in reader.fieldnames:
        raise ValueError("ecb reserves: CSV missing TIME_PERIOD column")
    rows: list[dict[str, Any]] = []
    for rec in reader:
        period = rec.get("TIME_PERIOD") or ""
        raw = (rec.get("OBS_VALUE") or "").strip()
        if not raw:
            log.warning("ecb reserves: no value for %s, skipped", period)
            continue
        try:
            mult = int(rec.get("UNIT_MULT") or 6)
            value = Decimal(raw) * (Decimal(10) ** mult)
            rows.append(
                {
                    "period_date": period_end(period),
                    "country_iso3": COUNTRY_ISO3,
                    "country": COUNTRY,
                    "metric": METRIC,
                    "value_usd": value,
                    "source": SOURCE_NAME,
                }
            )
        except (InvalidOperation, ValueError) as exc:
            log.warning("ecb reserves: skipping %s=%r: %s", period, raw, exc)
    return rows


def fetch(ctx: Ctx) -> Rows:
    resp = ctx.http.get(DATA_URL, params=PARAMS)
    resp.raise_for_status()
    rows = _parse_csv(resp.text)
    if not rows:
        raise ValueError("ecb reserves: no usable observations in response")
    log.info("ecb reserves: %d rows", len(rows))
    return [("reserves", rows)]


SOURCE = Source(
    name="reserves_ecb",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=["reserves"],
    description="ECB quarterly euro area official reserve assets (EUR, BPS dataflow)",
)

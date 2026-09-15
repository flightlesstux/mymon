"""World Bank annual official reserve assets (current US$) for every country.

Indicators:
  FI.RES.TOTL.CD  total reserves incl. gold   -> metric ``total``
  FI.RES.XGLD.CD  total reserves minus gold   -> metric ``ex_gold``
``gold`` is derived as ``total - ex_gold`` when both exist for a country/year.

One request per indicator returns the full 1960..today history (~17.5k records each), so
``fetch`` is the backfill and no separate ``backfill`` is needed. World Bank regional /
income aggregates are dropped except ``EMU`` (euro area) and ``WLD`` (world), which the
dashboards use directly. ``period_date`` is 31 December of the reference year.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

BASE_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicator}"
PARAMS = {"format": "json", "per_page": "20000", "date": "1960:2026"}

INDICATORS = {
    "FI.RES.TOTL.CD": "total",
    "FI.RES.XGLD.CD": "ex_gold",
}

# World Bank aggregate codes (region.id == "NA" in /v2/country). Kept: EMU, WLD.
AGGREGATES = frozenset(
    """
    AFE AFR AFW ARB BEA BEC BHI BLA BMN BSS CAA CEA CEB CEU CLA CME CSA CSS DEA DEC DLA DMN
    DNS DSA DSF DSS EAP EAR EAS ECA ECS EUU FXS HIC HPC IBB IBD IBT IDA IDB IDX INX LAC LCN
    LDC LIC LMC LMY LTE MDE MEA MIC MNA NAC NAF NRS NXS OED OSS PRE PSS PST RRS SAS SSA SSF
    SST SXZ TEA TEC TLA TMN TSA TSS UMC XZN
    """.split()
)
KEEP_AGGREGATES = frozenset({"EMU", "WLD"})

SOURCE_NAME = "worldbank"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _fetch_indicator(ctx: Ctx, indicator: str) -> dict[tuple[str, int], tuple[str, Decimal]]:
    """Return ``{(iso3, year): (country_name, value)}`` for one indicator."""
    resp = ctx.http.get(BASE_URL.format(indicator=indicator), params=PARAMS)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError(f"worldbank {indicator}: unexpected response shape")

    out: dict[tuple[str, int], tuple[str, Decimal]] = {}
    for rec in payload[1]:
        try:
            iso3 = (rec.get("countryiso3code") or "").strip().upper()
            value = _to_decimal(rec.get("value"))
            if not iso3 or value is None:
                continue
            if iso3 in AGGREGATES and iso3 not in KEEP_AGGREGATES:
                continue
            year = int(str(rec.get("date"))[:4])
            country = (rec.get("country") or {}).get("value") or iso3
            out[(iso3, year)] = (country, value)
        except (AttributeError, TypeError, ValueError) as exc:
            log.warning("worldbank %s: skipping record %r: %s", indicator, rec, exc)
    return out


def _row(iso3: str, year: int, country: str, metric: str, value: Decimal) -> dict[str, Any]:
    return {
        "period_date": date(year, 12, 31),
        "country_iso3": iso3,
        "country": country,
        "metric": metric,
        "value_usd": value,
        "source": SOURCE_NAME,
    }


def fetch(ctx: Ctx) -> Rows:
    series = {metric: _fetch_indicator(ctx, ind) for ind, metric in INDICATORS.items()}
    total, ex_gold = series["total"], series["ex_gold"]

    rows: list[dict[str, Any]] = []
    for (iso3, year), (country, value) in total.items():
        rows.append(_row(iso3, year, country, "total", value))
        xg = ex_gold.get((iso3, year))
        if xg is not None:
            rows.append(_row(iso3, year, country, "gold", value - xg[1]))
    for (iso3, year), (country, value) in ex_gold.items():
        rows.append(_row(iso3, year, country, "ex_gold", value))

    log.info("worldbank reserves: %d rows", len(rows))
    return [("reserves", rows)]


SOURCE = Source(
    name="reserves_worldbank",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=["reserves"],
    description="World Bank annual total reserves (incl./excl. gold, current US$) per country",
)

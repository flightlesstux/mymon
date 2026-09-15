"""Price-index source: World Bank macro indicators, the Economist Big Mac index, FAO food prices.

Everything lands in ``price_index`` (PK ``period_date, country_iso3, indicator, source``). The
three upstreams are small (a few thousand rows each) so every run re-pulls the full history and
there is no separate backfill. Each upstream is fetched independently: a failure in one is logged
and the others still produce rows; only when all three fail is an error raised.

Upstreams:
- World Bank API v2 (``source='worldbank'``): annual CPI inflation, PPP conversion factor and GDP
  per capita for every country. Records without an ISO3 code and the World Bank's regional /
  income aggregates are dropped (``WLD`` world and ``EMU`` euro area are kept).
  ``period_date`` is 31 December of the reference year.
- Economist Big Mac index (``source='economist'``): the ``big-mac-full-index.csv`` file from the
  public GitHub repo. ``iso_a3`` is stored as-is (it includes ``EUZ`` for the euro area).
- FAO Food Price Index (``source='fao'``): the CSV link is discovered from the FAO world food
  situation page because the document URL carries a changing version query string. The file has a
  couple of title lines before the header and pads every line with empty columns; the header names
  drift slightly (``Oils`` vs ``Vegetable Oils``), so columns are matched by keyword.
  Rows are global (``country_iso3='WLD'``) with ``period_date`` = first day of the month.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

WORLDBANK_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicator}"
WORLDBANK_PARAMS = {"format": "json", "per_page": "20000", "date": "1990:2026"}
BIGMAC_URL = (
    "https://raw.githubusercontent.com/TheEconomist/big-mac-data/master/"
    "output-data/big-mac-full-index.csv"
)
FAO_PAGE_URL = "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"
FAO_LINK_RE = re.compile(r"""[^"'\s<>]*food_price_indices_data[^"'\s<>]*?\.(csv|xlsx?)""", re.I)

TABLE = "price_index"

# World Bank indicator id -> (our indicator name, unit)
WB_INDICATORS: dict[str, tuple[str, str]] = {
    "FP.CPI.TOTL.ZG": ("cpi_inflation_pct", "%"),
    "PA.NUS.PPP": ("ppp_factor", "LCU per intl $"),
    "NY.GDP.PCAP.CD": ("gdp_per_capita_usd", "USD"),
}

# Regional / income / lending aggregates the World Bank mixes into ``country/all``.
# ``WLD`` (world) and ``EMU`` (euro area) are deliberately kept.
WB_AGGREGATES = frozenset(
    """
    EUU HIC LIC LMC LMY MIC UMC OED ARB EAS EAP ECS ECA LCN LAC MEA MNA NAC SAS SSF SSA
    CEB EAR FCS HPC IBD IBT IDA IDB IDX LDC LTE PRE PSS PST SST TEA TEC TLA TMN TSA TSS
    AFE AFW INX CSS OSS
    """.split()
)

FAO_UNIT = "index 2014-16=100"
# header keyword (lower-cased, matched by substring) -> indicator
FAO_COLUMNS: list[tuple[str, str]] = [
    ("food price index", "fao_food_index"),
    ("meat", "fao_meat"),
    ("dairy", "fao_dairy"),
    ("cereal", "fao_cereals"),
    ("oil", "fao_oils"),
    ("sugar", "fao_sugar"),
]


# --------------------------------------------------------------------------- helpers


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if not value:
            return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _row(period: date, iso3: str, indicator: str, value: float, unit: str, source: str) -> dict:
    return {
        "period_date": period,
        "country_iso3": iso3,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "source": source,
    }


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for r in rows:
        seen[(r["period_date"], r["country_iso3"], r["indicator"], r["source"])] = r
    return list(seen.values())


def _parse_month(value: str) -> date | None:
    """Accept ``1990-01``, ``1990-1``, ``1990/01``, ``Jan-1990``, ``Jan 1990``, ``1990-01-01``."""
    s = value.strip().strip('"')
    if not s:
        return None
    for fmt in ("%Y-%m", "%Y/%m", "%Y-%m-%d", "%b-%Y", "%b %Y", "%B-%Y", "%B %Y", "%Y%m", "%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().replace(day=1)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- World Bank


def _worldbank_records(payload: Any) -> list[dict]:
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("unexpected World Bank payload shape")
    return [r for r in payload[1] if isinstance(r, dict)]


def _worldbank_rows(payload: Any, indicator: str, unit: str) -> list[dict]:
    rows: list[dict] = []
    for rec in _worldbank_records(payload):
        iso3 = (rec.get("countryiso3code") or "").strip().upper()
        if not iso3 or iso3 in WB_AGGREGATES:
            continue
        value = _num(rec.get("value"))
        if value is None:
            continue
        try:
            year = int(str(rec.get("date"))[:4])
            period = date(year, 12, 31)
        except (TypeError, ValueError):
            log.warning(
                "price_indices: worldbank %s bad date %r for %s", indicator, rec.get("date"), iso3
            )
            continue
        rows.append(_row(period, iso3, indicator, value, unit, "worldbank"))
    return rows


def _fetch_worldbank(ctx: Ctx) -> list[dict]:
    rows: list[dict] = []
    for wb_id, (indicator, unit) in WB_INDICATORS.items():
        try:
            resp = ctx.http.get(WORLDBANK_URL.format(indicator=wb_id), params=WORLDBANK_PARAMS)
            resp.raise_for_status()
            part = _worldbank_rows(resp.json(), indicator, unit)
        except Exception as exc:  # noqa: BLE001 - one indicator must not sink the others
            log.warning("price_indices: worldbank %s failed: %s", wb_id, exc)
            continue
        log.info("price_indices: worldbank %s -> %d rows", wb_id, len(part))
        rows.extend(part)
    return rows


# --------------------------------------------------------------------------- Big Mac


def _bigmac_rows(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    required = {"date", "iso_a3", "local_price", "dollar_price"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(f"Big Mac CSV missing columns, got {reader.fieldnames}")
    has_raw = "USD_raw" in reader.fieldnames
    rows: list[dict] = []
    for rec in reader:
        iso3 = (rec.get("iso_a3") or "").strip().upper()
        raw_date = (rec.get("date") or "").strip()
        try:
            period = date.fromisoformat(raw_date[:10])
        except ValueError:
            log.warning("price_indices: bigmac bad date %r for %s, skipped", raw_date, iso3)
            continue
        if not iso3:
            log.warning("price_indices: bigmac row %s has no iso_a3, skipped", raw_date)
            continue
        usd = _num(rec.get("dollar_price"))
        if usd is not None:
            rows.append(_row(period, iso3, "bigmac_usd", usd, "USD", "economist"))
        local = _num(rec.get("local_price"))
        currency = (rec.get("currency_code") or "").strip().upper()
        if local is not None:
            rows.append(_row(period, iso3, "bigmac_local", local, currency or None, "economist"))
        if has_raw:
            raw = _num(rec.get("USD_raw"))
            if raw is not None:
                rows.append(
                    _row(period, iso3, "bigmac_usd_raw_pct", raw * 100.0, "%", "economist")
                )
    return rows


def _fetch_bigmac(ctx: Ctx) -> list[dict]:
    resp = ctx.http.get(BIGMAC_URL)
    resp.raise_for_status()
    return _bigmac_rows(resp.content.decode("utf-8-sig", errors="replace"))


# --------------------------------------------------------------------------- FAO


def _fao_csv_url(html: str) -> str:
    links = [m.group(0) for m in FAO_LINK_RE.finditer(html)]
    if not links:
        raise ValueError("no food_price_indices_data link found on FAO page")
    csvs = [x for x in links if x.lower().endswith(".csv")]
    link = (csvs or links)[0].replace("&amp;", "&")
    if link.startswith("//"):
        link = "https:" + link
    elif link.startswith("/"):
        link = "https://www.fao.org" + link
    return link


def _fao_header_map(header: list[str]) -> dict[int, str]:
    """Column index -> indicator, matched by keyword so minor header renames keep working."""
    out: dict[int, str] = {}
    for idx, name in enumerate(header):
        lname = name.strip().lower()
        if not lname:
            continue
        for key, indicator in FAO_COLUMNS:
            if key in lname and indicator not in out.values():
                out[idx] = indicator
                break
    return out


def _fao_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    colmap: dict[int, str] = {}
    date_col = 0
    for rec in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in rec]
        if not any(cells):
            continue
        if not colmap:
            lowered = [c.lower() for c in cells]
            if "date" in lowered:
                date_col = lowered.index("date")
                colmap = _fao_header_map(cells)
                if not colmap:
                    raise ValueError(f"FAO header has no known columns: {cells[:8]}")
            continue
        if date_col >= len(cells):
            continue
        period = _parse_month(cells[date_col])
        if period is None:
            log.warning("price_indices: fao bad date %r, skipped", cells[date_col])
            continue
        for idx, indicator in colmap.items():
            value = _num(cells[idx]) if idx < len(cells) else None
            if value is None:
                continue
            rows.append(_row(period, "WLD", indicator, value, FAO_UNIT, "fao"))
    if not colmap:
        raise ValueError("FAO CSV has no header line containing 'Date'")
    return rows


def _fao_xlsx_rows(content: bytes) -> list[dict]:
    """Fallback when only the XLS(X) variant is linked; same layout as the CSV."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in ws.iter_rows(values_only=True):
        cells = []
        for c in row:
            if isinstance(c, datetime | date):
                cells.append(c.strftime("%Y-%m"))
            else:
                cells.append("" if c is None else str(c))
        writer.writerow(cells)
    return _fao_rows(buf.getvalue())


def _fetch_fao(ctx: Ctx) -> list[dict]:
    page = ctx.http.get(FAO_PAGE_URL)
    page.raise_for_status()
    url = _fao_csv_url(page.text)
    resp = ctx.http.get(url)
    resp.raise_for_status()
    if url.lower().split("?")[0].endswith(".csv"):
        return _fao_rows(resp.content.decode("utf-8-sig", errors="replace"))
    return _fao_xlsx_rows(resp.content)


# --------------------------------------------------------------------------- source


def fetch(ctx: Ctx) -> Rows:
    rows: list[dict] = []
    failures = 0
    upstreams = (("worldbank", _fetch_worldbank), ("bigmac", _fetch_bigmac), ("fao", _fetch_fao))
    for name, fn in upstreams:
        try:
            part = fn(ctx)
        except Exception as exc:  # noqa: BLE001 - keep the other upstreams alive
            log.warning("price_indices: %s failed: %s", name, exc)
            failures += 1
            continue
        if not part:
            log.warning("price_indices: %s returned no rows", name)
            failures += 1
            continue
        log.info("price_indices: %s -> %d rows", name, len(part))
        rows.extend(part)
    if not rows:
        raise RuntimeError("price_indices: every upstream failed")
    return [(TABLE, _dedupe(rows))]


SOURCE = Source(
    name="price_indices",
    interval=86400,
    fetch=fetch,
    backfill=None,
    tables=[TABLE],
    description="World Bank CPI/PPP/GDP per capita, Economist Big Mac index, FAO food price index",
)

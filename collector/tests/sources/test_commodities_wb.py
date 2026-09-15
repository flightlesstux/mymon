from __future__ import annotations

import io
from datetime import date

import httpx
import openpyxl
import respx

from mymon_collector.sources import commodities_wb

DOC_URL = (
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026"
    "/related/CMO-Historical-Data-Monthly.xlsx"
)
PAGE_HTML = f"""
<html><body>
<a href="https://thedocs.worldbank.org/en/doc/x-0050012026/related/CMO-Historical-Data-Annual.xlsx">annual</a>
<a href="{DOC_URL}">monthly</a>
</body></html>
"""


def build_xlsx() -> bytes:
    """First rows of the live 'Monthly Prices' sheet: titles, names, units, YYYYMmm rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Mismatch Details"
    ws.append(["unrelated"])
    ws = wb.create_sheet("Monthly Prices")
    ws.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    ws.append(["monthly prices in nominal US dollars, 1960 to present"])
    ws.append(["(monthly series are available from 1960M01)"])
    ws.append(["Updated on September 03, 2026"])
    ws.append(
        [
            None,
            "Crude oil, average",
            "Crude oil, Brent",
            "Natural gas, Europe",
            "Coffee, Arabica",
            "Coal, South African **",
            "Gold",
        ]
    )
    ws.append([None, "($/bbl)", "($/bbl)", "($/mmbtu)", "($/kg)", "($/mt)", "($/troy oz)"])
    ws.append(["1960M01", 1.63000011444, 1.63000011444, 0.40477399635, 0.9, "…", 35.27])
    ws.append(["2026M08", "84.4", 90.9, 11.2, "", "…", None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_slugify():
    assert commodities_wb.slugify("Crude oil, Brent") == "crude_oil_brent"
    assert commodities_wb.slugify("Coal, South African **") == "coal_south_african"
    assert commodities_wb.slugify("Rice, Thai 5% ") == "rice_thai_5"


@respx.mock
def test_fetch_discovers_link_and_parses(ctx):
    respx.get(commodities_wb.PAGE_URL).mock(return_value=httpx.Response(200, text=PAGE_HTML))
    respx.get(DOC_URL).mock(return_value=httpx.Response(200, content=build_xlsx()))
    fallback = respx.get(commodities_wb.FALLBACK_URL).mock(return_value=httpx.Response(404))

    out = commodities_wb.fetch(ctx)
    assert not fallback.called
    assert [t for t, _ in out] == ["commodity_price"]
    rows = out[0][1]
    # 1960M01: 5 values ('…' skipped); 2026M08: 3 values ('', '…', None skipped)
    assert len(rows) == 8
    for r in rows:
        assert {"period_date", "commodity", "source"} <= set(r)
        assert r["source"] == "wb_pink"

    by_key = {(r["period_date"], r["commodity"]): r for r in rows}
    brent = by_key[(date(1960, 1, 1), "crude_oil_brent")]
    assert brent["price"] == 1.63000011444 and brent["unit"] == "$/bbl"
    assert by_key[(date(2026, 8, 1), "crude_oil_average")]["price"] == 84.4
    gas = by_key[(date(2026, 8, 1), "natural_gas_europe")]
    assert gas["price"] == 11.2 and gas["unit"] == "$/mmbtu"
    assert by_key[(date(1960, 1, 1), "gold")]["unit"] == "$/troy oz"
    assert (date(1960, 1, 1), "coal_south_african") not in by_key
    assert (date(2026, 8, 1), "gold") not in by_key


@respx.mock
def test_fetch_falls_back_to_fixed_url(ctx):
    respx.get(commodities_wb.PAGE_URL).mock(return_value=httpx.Response(503))
    respx.get(commodities_wb.FALLBACK_URL).mock(
        return_value=httpx.Response(200, content=build_xlsx())
    )
    out = commodities_wb.fetch(ctx)
    assert len(out[0][1]) == 8

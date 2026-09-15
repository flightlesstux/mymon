from __future__ import annotations

import io
from datetime import date, datetime

import httpx
import openpyxl
import respx

from mymon_collector.sources import fuel_eu

PAGE_HTML = (
    "<html><body>\n"
    '<a href="/document/download/aaa_en?filename=Weekly%20Oil%20Bulletin%20Weekly%20prices'
    '%20with%20Taxes%20-%202024-02-19.xlsx">weekly</a>\n'
    '<a href="/document/download/bbb_en?filename=Oil_Bulletin_Duties_and_taxes.xlsx">duties</a>\n'
    '<a href="/document/download/906e60ca_en?filename=Weekly_Oil_Bulletin_Prices_History_mat'
    'icni_4web.xlsx">history</a>\n'
    "</body></html>\n"
)
XLSX_URL = (
    "https://energy.ec.europa.eu/document/download/906e60ca_en"
    "?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx"
)


def _block(code: str) -> list[str]:
    p = f"{code}_price_with_tax_"
    return [
        "CTR",
        p + "euro95",
        p + "diesel",
        p + "heating_oil",
        p + "fuel_oil_1",
        p + "fuel_oil_2",
        p + "LPG",
    ]


def build_xlsx() -> bytes:
    """Same layout as the live file: id row, label row, unit row, then dates newest first."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prices with taxes"
    ws.append(
        ["Consumer prices of petroleum products"] + _block("EU") + _block("EUR") + _block("AT")
    )
    ws.append(
        [None, None, "Euro-super 95  (I)", "Gas oil automobile", "Heating", "FO1", "FO2", "LPG"]
    )
    ws.append(["Date", None, "1000 l", "1000 l", "1000 l", "t", "t", "1000 l"])
    ws.append(
        [datetime(2026, 9, 7)]
        + ["EU_", 2041.6684660061321, 2107.3855574757486, 1595.2, 668.1, 570.5, 850.28]
        + ["EUR_", 2099.8, 2150.1, 1600.0, 670.0, 571.0, 860.0]
        + ["AT_", 1912, 2126, 1400, None, None, None]
    )
    ws.append(
        [datetime(2026, 8, 31)]
        + ["EU_", 1949.99, 2039.15, 1472.9, 701.9, 530.9, 845.7]
        + ["EUR_", 2026.5, 2080.0, 1500.0, 650.0, 560.0, 850.0]
        + ["AT_", 1890.5, 2100.25, 1390, None, None, 760.0]
    )
    ws.append([None, None, None, None, None, None, None, None])
    ws.append(["Notes: (I) prices in EUR per 1000 l"])
    wb.create_sheet("Prices wo taxes").append(["ignored"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_discover_prefers_history_link():
    assert fuel_eu.discover_xlsx_url(PAGE_HTML) == XLSX_URL
    assert fuel_eu.discover_xlsx_url("<html>no links</html>") is None


@respx.mock
def test_fetch_parses_history(ctx):
    respx.get(fuel_eu.PAGE_URL).mock(return_value=httpx.Response(200, text=PAGE_HTML))
    respx.get(XLSX_URL).mock(return_value=httpx.Response(200, content=build_xlsx()))

    out = fuel_eu.fetch(ctx)
    assert [t for t, _ in out] == ["fuel_price"]
    rows = out[0][1]
    # EU: 3 fuels x 2 dates, AT: 2 fuels on 09-07 + 3 fuels on 08-31; EUR_ aggregate dropped
    assert len(rows) == 6 + 5
    assert {r["country_iso2"] for r in rows} == {"EU", "AT"}

    pk = {"period_date", "country_iso2", "region", "fuel_type", "source"}
    for r in rows:
        assert pk <= set(r)
        assert r["region"] == ""
        assert r["currency"] == "EUR" and r["unit"] == "EUR/L" and r["source"] == "eu_wob"

    by_key = {(r["period_date"], r["country_iso2"], r["fuel_type"]): r["price"] for r in rows}
    assert by_key[(date(2026, 9, 7), "AT", "petrol95")] == 1.912
    assert by_key[(date(2026, 9, 7), "AT", "diesel")] == 2.126
    assert by_key[(date(2026, 9, 7), "EU", "petrol95")] == 2.0417
    assert by_key[(date(2026, 8, 31), "AT", "lpg")] == 0.76
    assert (date(2026, 9, 7), "AT", "lpg") not in by_key


@respx.mock
def test_fetch_fails_without_link(ctx):
    respx.get(fuel_eu.PAGE_URL).mock(return_value=httpx.Response(200, text="<html></html>"))
    try:
        fuel_eu.fetch(ctx)
    except ValueError as exc:
        assert "XLSX" in str(exc)
    else:
        raise AssertionError("expected ValueError")

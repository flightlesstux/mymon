from datetime import date, datetime

import httpx
import respx

from mymon_collector.sources import country_indices as ci


def chart_json(timestamps, closes):
    return {
        "chart": {
            "result": [{
                "meta": {"currency": "EUR"},
                "timestamp": timestamps,
                "indicators": {"quote": [{"close": closes}]},
            }],
            "error": None,
        }
    }


@respx.mock
def test_fetch_parses_all_indices():
    for ticker in ci.INDICES:
        respx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}").mock(
            return_value=httpx.Response(200, json=chart_json(
                [1757894400, 1757980800], [20000.0, 20100.5],
            ))
        )
    rows = ci.fetch(_ctx())
    table, data = rows[0]
    assert table == "stock_index"
    symbols = {r["symbol"] for r in data}
    assert symbols == set(ci.INDICES.values())
    dax_rows = [r for r in data if r["symbol"] == "DAX"]
    latest = max(dax_rows, key=lambda r: r["day"])
    assert latest["close"] == 20100.5
    assert latest["day"] == date(2025, 9, 16)
    # rows are just {day, symbol, close} — no company-name/currency fields like nl_us_stock
    assert set(latest.keys()) == {"day", "symbol", "close"}


@respx.mock
def test_fetch_drops_null_close_and_skips_dead_ticker():
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGDAXI").mock(
        return_value=httpx.Response(200, json=chart_json(
            [1757894400, 1757980800], [20000.0, None],
        ))
    )
    for ticker in ci.INDICES:
        if ticker == "^GDAXI":
            continue
        respx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}").mock(
            return_value=httpx.Response(200, json={"chart": {"result": None,
                                                               "error": {"code": "Not Found"}}})
        )
    table, data = ci.fetch(_ctx())[0]
    assert len(data) == 1
    assert data[0]["close"] == 20000.0


def _ctx():
    return ci.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

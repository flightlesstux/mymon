from datetime import datetime

import httpx
import respx

from mymon_collector.sources import nl_us_stocks as st


def chart_json(symbol, timestamps, closes, volumes, currency="USD"):
    return {
        "chart": {
            "result": [{
                "meta": {"currency": currency, "symbol": symbol},
                "timestamp": timestamps,
                "indicators": {"quote": [{"close": closes, "volume": volumes}]},
            }],
            "error": None,
        }
    }


@respx.mock
def test_fetch_parses_all_symbols():
    for symbol in st.SYMBOLS:
        respx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}").mock(
            return_value=httpx.Response(200, json=chart_json(
                symbol,
                [1757894400, 1757980800],  # 2025-09-15, 2025-09-16 UTC midnight
                [123.45, 124.5],
                [1000, 2000],
            ))
        )
    rows = st.fetch(_ctx())
    table, data = rows[0]
    assert table == "nl_us_stock"
    symbols = {r["symbol"] for r in data}
    assert symbols == set(st.SYMBOLS)
    asml_rows = [r for r in data if r["symbol"] == "ASML"]
    assert len(asml_rows) == 2
    latest = max(asml_rows, key=lambda r: r["day"])
    assert latest["name"] == "ASML Holding"
    assert latest["currency"] == "USD"
    assert latest["source"] == "yahoo_finance"
    assert latest["close"] == 124.5


@respx.mock
def test_fetch_drops_null_close_and_skips_dead_symbol():
    respx.get("https://query1.finance.yahoo.com/v8/finance/chart/ASML").mock(
        return_value=httpx.Response(200, json=chart_json(
            "ASML", [1757894400, 1757980800], [123.45, None], [1000, 2000],
        ))
    )
    for symbol in st.SYMBOLS:
        if symbol == "ASML":
            continue
        respx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}").mock(
            return_value=httpx.Response(200, json={"chart": {"result": None,
                                                               "error": {"code": "Not Found"}}})
        )
    rows = st.fetch(_ctx())
    _, data = rows[0]
    assert len(data) == 1
    assert data[0]["close"] == 123.45


def _ctx():
    return st.Ctx(http=httpx.Client(), cfg={"cities": [], "env": {}}, now=datetime(2026, 9, 16))

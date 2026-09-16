from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from mymon_collector.sources import crypto
from tests.conftest import fixture_json

TICKER_RE = r"https://api\.binance\.com/api/v3/ticker/24hr\?symbols=%5B%22BTCUSDT%22.*%5D$"
KLINES_RE = r"https://api\.binance\.com/api/v3/klines\?.*"
COINGECKO_RE = r"https://api\.coingecko\.com/api/v3/simple/price\?.*ids=bitcoin.*"


def test_source_metadata():
    assert crypto.SOURCE.name == "crypto"
    assert crypto.SOURCE.interval == 60
    assert crypto.SOURCE.tables == ["crypto_tick", "crypto_daily"]
    assert crypto.SOURCE.backfill is not None


def test_symbols_param_is_compact_json():
    assert crypto._symbols_param() == (
        '["BTCUSDT","ETHUSDT","SOLUSDT","PAXGUSDT","BNBUSDT","XRPUSDT",'
        '"ADAUSDT","DOGEUSDT","DOTUSDT","AVAXUSDT","LINKUSDT","LTCUSDT"]'
    )


@respx.mock
def test_fetch_binance_primary(ctx):
    # only Binance is mocked: any CoinGecko call would fail as an unmocked request
    route = respx.get(url__regex=TICKER_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("crypto_binance_ticker.json"))
    )

    out = crypto.fetch(ctx)

    assert route.call_count == 1
    assert [t for t, _ in out] == ["crypto_tick"]
    rows = out[0][1]
    assert len(rows) == len(crypto.SYMBOLS)
    assert all({"ts", "symbol"} <= r.keys() for r in rows)
    assert {r["symbol"] for r in rows} == set(crypto.SYMBOLS)

    btc = next(r for r in rows if r["symbol"] == "BTC")
    assert btc["ts"] == datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert btc["price"] == Decimal("76837.30000000")
    assert btc["volume_24h"] == Decimal("2315721.56671790")
    assert btc["change_24h_pct"] == Decimal("-2.995")


@respx.mock
def test_fetch_falls_back_to_coingecko_on_451(ctx):
    respx.get(url__regex=TICKER_RE).mock(return_value=httpx.Response(451))
    gecko = respx.get(url__regex=COINGECKO_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("crypto_coingecko_price.json"))
    )

    rows = crypto.fetch(ctx)[0][1]

    assert gecko.called
    assert len(rows) == len(crypto.SYMBOLS)
    btc = next(r for r in rows if r["symbol"] == "BTC")
    assert btc["price"] == Decimal("76611")
    assert btc["ts"] == datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert btc["change_24h_pct"] is not None
    assert all({"ts", "symbol", "price"} <= r.keys() for r in rows)


@respx.mock
def test_fetch_raises_when_all_providers_fail(ctx):
    respx.get(url__regex=TICKER_RE).mock(return_value=httpx.Response(451))
    respx.get(url__regex=COINGECKO_RE).mock(return_value=httpx.Response(429))
    with pytest.raises(httpx.HTTPStatusError):
        crypto.fetch(ctx)


def test_ticker_skips_bad_entries():
    ts = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    rows = crypto.parse_binance_ticker(
        [{"symbol": "BTCUSDT", "lastPrice": "1.5"}, {"symbol": "ETHUSDT"}, "junk"], ts
    )
    assert [r["symbol"] for r in rows] == ["BTC"]
    assert rows[0]["volume_24h"] is None


@respx.mock
def test_backfill_pages_klines_backwards(ctx):
    klines = fixture_json("crypto_binance_klines.json")  # 5 daily candles
    route = respx.get(url__regex=KLINES_RE).mock(return_value=httpx.Response(200, json=klines))

    out = crypto.backfill(ctx)

    assert [t for t, _ in out] == ["crypto_daily"]
    rows = out[0][1]
    # a page smaller than the limit ends paging: one request per symbol
    assert route.call_count == len(crypto.SYMBOLS)
    assert len(rows) == 5 * len(crypto.SYMBOLS)
    assert all({"day", "symbol"} <= r.keys() for r in rows)
    first_req = route.calls[0].request
    assert first_req.url.params["symbol"] == "BTCUSDT"
    assert first_req.url.params["interval"] == "1d"
    assert first_req.url.params["limit"] == "1000"
    assert "endTime" not in first_req.url.params

    btc = sorted((r for r in rows if r["symbol"] == "BTC"), key=lambda r: r["day"])
    assert btc[0]["day"] == date(2023, 12, 21)
    assert btc[0]["open"] == Decimal("43668.92000000")
    assert btc[0]["high"] == Decimal("44242.35000000")
    assert btc[0]["close"] == Decimal("43861.80000000")
    assert btc[0]["volume"] == Decimal("34624.29384000")


@respx.mock
def test_backfill_uses_end_time_for_second_page(ctx, monkeypatch):
    # build a full 1000-candle page ending today so a second page is requested
    day_ms = 86_400_000
    end_open = int(datetime(2026, 9, 14, tzinfo=UTC).timestamp() * 1000)
    full_page = [
        [end_open - (999 - i) * day_ms, "1", "2", "0.5", "1.5", "10", 0] for i in range(1000)
    ]
    oldest_open = end_open - 1000 * day_ms
    older = [[oldest_open, "1", "2", "0.5", "1.5", "10", 0]]

    def responder(request):
        if "endTime" in request.url.params:
            return httpx.Response(200, json=older)
        return httpx.Response(200, json=full_page)

    route = respx.get(url__regex=KLINES_RE).mock(side_effect=responder)
    monkeypatch.setattr(crypto, "SYMBOLS", ["BTC"])

    rows = crypto.backfill(ctx)[0][1]

    assert route.call_count == 2
    second = route.calls[1].request
    assert int(second.url.params["endTime"]) == full_page[0][0] - 1
    assert len(rows) == 1001
    expected_oldest = datetime.fromtimestamp(oldest_open / 1000, tz=UTC).date()
    assert min(r["day"] for r in rows) == expected_oldest
    assert expected_oldest < date(2024, 1, 1)

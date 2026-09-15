from __future__ import annotations

import hashlib
from datetime import date

import httpx
import respx

from mymon_collector.sources import commodities_stooq as stooq

CHALLENGE = "test-challenge-token"
DIFFICULTY = 1  # keep the proof-of-work cheap in tests


def _find_nonce(challenge: str, difficulty: int) -> int:
    prefix = "0" * difficulty
    n = 0
    while not hashlib.sha256(f"{challenge}{n}".encode()).hexdigest().startswith(prefix):
        n += 1
    return n


CHALLENGE_HTML = (
    '<script>(async()=>{const c="' + CHALLENGE + f'",d={DIFFICULTY},t="0".repeat(d)'
    ";})();</script>"
)


def _csv(rows: list[tuple[str, float]]) -> str:
    lines = ["Date,Open,High,Low,Close,Volume"]
    for day, close in rows:
        lines.append(f"{day},{close},{close},{close},{close},1000")
    return "\n".join(lines) + "\n"


def _series(n: int, start_close: float = 100.0) -> list[tuple[str, float]]:
    return [(f"2026-08-{i + 1:02d}", start_close + i) for i in range(n)]


def test_parse_csv_skips_bad_rows():
    text = _csv([("2026-09-01", 10.5), ("2026-09-02", 11.0)]) + "garbage,,,,,\n"
    out = stooq.parse_csv(text)
    assert out == [(date(2026, 9, 1), 10.5), (date(2026, 9, 2), 11.0)]


def test_solve_challenge_finds_valid_nonce():
    nonce = stooq.solve_challenge(CHALLENGE, DIFFICULTY)
    assert nonce is not None
    digest = hashlib.sha256(f"{CHALLENGE}{nonce}".encode()).hexdigest()
    assert digest.startswith("0" * DIFFICULTY)


@respx.mock
def test_download_solves_challenge_then_retries(ctx):
    calls = {"n": 0}

    def _get(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, text=CHALLENGE_HTML)
        return httpx.Response(200, text=_csv([("2026-09-01", 10.5)]))

    respx.get(stooq.BASE_URL, params={"s": "cb.f", "i": "d"}).mock(side_effect=_get)
    verify = respx.post(stooq.VERIFY_URL).mock(return_value=httpx.Response(200))

    out = stooq._download(ctx, "cb.f")
    assert out == [(date(2026, 9, 1), 10.5)]
    assert verify.called
    sent = dict(x.split("=") for x in verify.calls.last.request.content.decode().split("&"))
    assert sent["c"] == CHALLENGE


@respx.mock
def test_download_returns_none_on_denied(ctx):
    respx.get(stooq.BASE_URL, params={"s": "xauusd", "i": "d"}).mock(
        return_value=httpx.Response(200, text="Access denied")
    )
    assert stooq._download(ctx, "xauusd") is None


@respx.mock
def test_fetch_keeps_tail_and_skips_dead_symbols(ctx):
    series15 = _series(15)
    for symbol in stooq.COMMODITIES:
        if symbol == "hg.f":
            respx.get(stooq.BASE_URL, params={"s": symbol, "i": "d"}).mock(
                return_value=httpx.Response(200, text="Exceeded the daily hits limit")
            )
        else:
            respx.get(stooq.BASE_URL, params={"s": symbol, "i": "d"}).mock(
                return_value=httpx.Response(200, text=_csv(series15))
            )
    for name, candidates in stooq.INDICES.items():
        primary = candidates[0]
        if name == "XU100":
            respx.get(stooq.BASE_URL, params={"s": "xu100", "i": "d"}).mock(
                return_value=httpx.Response(200, text="Access denied")
            )
            respx.get(stooq.BASE_URL, params={"s": "^xu100", "i": "d"}).mock(
                return_value=httpx.Response(200, text="Access denied")
            )
        else:
            respx.get(stooq.BASE_URL, params={"s": primary, "i": "d"}).mock(
                return_value=httpx.Response(200, text=_csv(series15))
            )

    out = stooq.fetch(ctx)
    tables = {t: rows for t, rows in out}
    assert set(tables) == {"commodity_price", "stock_index"}

    commodity_rows = tables["commodity_price"]
    commodities_seen = {r["commodity"] for r in commodity_rows}
    assert "copper" not in commodities_seen  # hg.f was rate-limited
    assert commodities_seen == {"brent", "wti", "natural_gas_us", "gold", "silver"}
    for r in commodity_rows:
        assert {"period_date", "commodity", "price", "unit", "source"} <= set(r)
        assert r["source"] == "stooq"
    per_symbol = [r for r in commodity_rows if r["commodity"] == "brent"]
    assert len(per_symbol) == stooq.FETCH_TAIL  # tail-limited to last 10 of 15 rows
    assert {r["price"] for r in per_symbol} == {100.0 + i for i in range(5, 15)}

    index_rows = tables["stock_index"]
    symbols_seen = {r["symbol"] for r in index_rows}
    assert "XU100" not in symbols_seen  # both candidates denied
    assert symbols_seen == {"SPX", "DJI", "NDQ", "DAX", "UKX", "NKX"}
    for r in index_rows:
        assert {"day", "symbol", "close"} <= set(r)
    spx_rows = [r for r in index_rows if r["symbol"] == "SPX"]
    assert len(spx_rows) == stooq.FETCH_TAIL


@respx.mock
def test_backfill_keeps_full_history(ctx):
    series15 = _series(15)
    for symbol in stooq.COMMODITIES:
        respx.get(stooq.BASE_URL, params={"s": symbol, "i": "d"}).mock(
            return_value=httpx.Response(200, text=_csv(series15))
        )
    for candidates in stooq.INDICES.values():
        respx.get(stooq.BASE_URL, params={"s": candidates[0], "i": "d"}).mock(
            return_value=httpx.Response(200, text=_csv(series15))
        )

    out = stooq.backfill(ctx)
    tables = {t: rows for t, rows in out}
    brent_rows = [r for r in tables["commodity_price"] if r["commodity"] == "brent"]
    assert len(brent_rows) == 15
    spx_rows = [r for r in tables["stock_index"] if r["symbol"] == "SPX"]
    assert len(spx_rows) == 15

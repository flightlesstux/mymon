from datetime import UTC, datetime

import httpx
import pytest
import respx

from mymon_collector.sources import btc_network as mod
from tests.conftest import fixture_json, fixture_text

PK = {"ts"}


def _mock_all():
    respx.get(mod.FEES_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("btc_network_fees.json"))
    )
    respx.get(mod.TIP_URL).mock(
        return_value=httpx.Response(200, text=fixture_text("btc_network_tip_height.txt"))
    )
    respx.get(mod.MEMPOOL_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("btc_network_mempool.json"))
    )
    respx.get(mod.HASHRATE_3D_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("btc_network_hashrate_3d.json"))
    )


@respx.mock
def test_fetch(ctx):
    _mock_all()
    ctx.now = datetime(2026, 9, 15, 12, 0, 42, 123456, tzinfo=UTC)
    out = mod.fetch(ctx)
    assert [t for t, _ in out] == ["btc_network"]
    rows = out[0][1]
    assert len(rows) == 1
    row = rows[0]
    assert row["ts"] == datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert row["block_height"] == 967174
    assert row["fee_fast"] == 3
    assert row["fee_half_hour"] == 3
    assert row["fee_hour"] == 1
    assert row["fee_economy"] == 1
    assert row["mempool_tx_count"] == 77775
    assert row["mempool_vsize"] == 39857586
    assert row["hashrate_ehs"] == pytest.approx(982.6851117309269)
    assert row["difficulty"] == pytest.approx(127450789715843.1)
    assert set(row) == set(mod.COLUMNS)
    assert PK <= row.keys()


@respx.mock
def test_fetch_partial_failure(ctx):
    _mock_all()
    respx.get(mod.HASHRATE_3D_URL).mock(return_value=httpx.Response(503))
    row = mod.fetch(ctx)[0][1][0]
    assert row["hashrate_ehs"] is None
    assert row["difficulty"] is None
    assert row["block_height"] == 967174


@respx.mock
def test_fetch_all_failed_raises(ctx):
    for url in (mod.FEES_URL, mod.TIP_URL, mod.MEMPOOL_URL, mod.HASHRATE_3D_URL):
        respx.get(url).mock(return_value=httpx.Response(500))
    with pytest.raises(RuntimeError):
        mod.fetch(ctx)


@respx.mock
def test_backfill(ctx):
    respx.get(mod.HASHRATE_1Y_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("btc_network_hashrate_1y.json"))
    )
    out = mod.backfill(ctx)
    assert [t for t, _ in out] == ["btc_network"]
    rows = out[0][1]
    assert len(rows) == 5
    assert rows[0]["ts"] == datetime.fromtimestamp(1757980800, tz=UTC)
    assert rows[0]["hashrate_ehs"] == pytest.approx(1099.657107671374)
    assert rows[0]["difficulty"] is None  # before the first adjustment in the window
    assert rows[3]["difficulty"] == pytest.approx(142342602928674.9)
    assert rows[0]["block_height"] is None
    assert rows[0]["fee_fast"] is None
    assert all(set(r) == set(mod.COLUMNS) for r in rows)
    assert all(PK <= r.keys() for r in rows)

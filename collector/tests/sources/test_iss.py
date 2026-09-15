from datetime import UTC, datetime

import httpx
import pytest
import respx

from mymon_collector.sources import iss as mod
from tests.conftest import fixture_json

PK = {"ts"}


@respx.mock
def test_fetch(ctx):
    respx.get(mod.URL).mock(return_value=httpx.Response(200, json=fixture_json("iss_25544.json")))
    out = mod.fetch(ctx)
    assert [t for t, _ in out] == ["iss_position"]
    rows = out[0][1]
    assert len(rows) == 1
    row = rows[0]
    assert row["ts"] == datetime.fromtimestamp(1789496995, tz=UTC)
    assert row["lat"] == pytest.approx(51.202609322775)
    assert row["lon"] == pytest.approx(17.883284159259)
    assert row["altitude_km"] == pytest.approx(423.64334025962)
    assert row["velocity_kmh"] == pytest.approx(27591.774436606)
    assert PK <= row.keys()
    assert mod.SOURCE.backfill is None


@respx.mock
def test_unusable_response_raises(ctx):
    respx.get(mod.URL).mock(return_value=httpx.Response(200, json={"error": "nope"}))
    with pytest.raises(ValueError):
        mod.fetch(ctx)

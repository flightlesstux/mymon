from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from mymon_collector.sources import opensky
from tests.conftest import fixture_json

STATES_RE = r"https://opensky-network\.org/api/states/all\?.*"
COLS = {"ts", "icao24", "callsign", "country", "lat", "lon", "alt_m", "velocity", "heading"}
SNAPSHOT_TS = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)  # epoch 1789560000


@pytest.fixture
def keyed_ctx(ctx):
    opensky._reset_token_cache()
    ctx.cfg["env"]["OPENSKY_CLIENT_ID"] = "test"
    ctx.cfg["env"]["OPENSKY_CLIENT_SECRET"] = "test"
    yield ctx
    opensky._reset_token_cache()


def _mock_token():
    return respx.post(opensky.TOKEN_URL).mock(
        return_value=httpx.Response(200, json=fixture_json("opensky_token.json"))
    )


def _mock_states():
    return respx.get(url__regex=STATES_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("opensky_states.json"))
    )


def test_source_metadata():
    assert opensky.SOURCE.name == "opensky"
    assert opensky.SOURCE.interval == 300
    assert opensky.SOURCE.requires_env == ["OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET"]
    assert opensky.SOURCE.tables == ["aircraft_state"]
    assert opensky.SOURCE.backfill is None


@respx.mock
def test_fetch_authenticates_and_parses_state_vectors(keyed_ctx):
    token_route = _mock_token()
    states_route = _mock_states()

    out = opensky.fetch(keyed_ctx)
    assert [t for t, _ in out] == ["aircraft_state"]
    assert token_route.call_count == 1
    assert states_route.call_count == 1

    token_req = token_route.calls[0].request
    body = token_req.content.decode()
    assert "grant_type=client_credentials" in body
    assert "client_id=test" in body and "client_secret=test" in body
    states_req = states_route.calls[0].request
    assert states_req.headers["Authorization"] == "Bearer eyJhbGciOiJSUzI1NiJ9.test-token"
    params = states_req.url.params
    assert (params["lamin"], params["lomin"], params["lamax"], params["lomax"]) == (
        "34", "-12", "62", "45"
    )

    rows = out[0][1]
    assert len(rows) == 3  # no-position vector and duplicate icao24 skipped
    assert all(COLS == set(r) for r in rows)
    assert all(r["ts"] == SNAPSHOT_TS for r in rows)
    by_icao = {r["icao24"]: r for r in rows}
    assert set(by_icao) == {"4b1805", "4ba9c1", "406b7e"}
    swr = by_icao["4b1805"]
    assert swr == {
        "ts": SNAPSHOT_TS,
        "icao24": "4b1805",
        "callsign": "SWR123",
        "country": "Switzerland",
        "lat": 47.4582,
        "lon": 8.5492,
        "alt_m": 10668.0,
        "velocity": 231.5,
        "heading": 87.3,
    }
    thy = by_icao["4ba9c1"]
    assert thy["callsign"] == "THY7NJ" and thy["lat"] == 41.2753 and thy["velocity"] == 120.1
    ground = by_icao["406b7e"]
    assert ground["callsign"] is None
    assert ground["alt_m"] == 20.4  # geo altitude fallback when baro is null
    assert ground["heading"] == 270.0


@respx.mock
def test_token_is_cached_between_polls(keyed_ctx):
    token_route = _mock_token()
    states_route = _mock_states()
    opensky.fetch(keyed_ctx)
    opensky.fetch(keyed_ctx)
    assert token_route.call_count == 1
    assert states_route.call_count == 2


@respx.mock
def test_token_refreshed_after_401(keyed_ctx):
    token_route = _mock_token()
    states_route = respx.get(url__regex=STATES_RE).mock(
        side_effect=[
            httpx.Response(401, text="expired"),
            httpx.Response(200, json=fixture_json("opensky_states.json")),
        ]
    )
    rows = opensky.fetch(keyed_ctx)[0][1]
    assert len(rows) == 3
    assert token_route.call_count == 2
    assert states_route.call_count == 2


@respx.mock
def test_null_states_yields_no_rows(keyed_ctx):
    _mock_token()
    respx.get(url__regex=STATES_RE).mock(
        return_value=httpx.Response(200, json={"time": 1789560000, "states": None})
    )
    assert opensky.fetch(keyed_ctx) == [("aircraft_state", [])]


@respx.mock
def test_bad_token_response_raises(keyed_ctx):
    respx.post(opensky.TOKEN_URL).mock(return_value=httpx.Response(200, json={"error": "x"}))
    with pytest.raises(ValueError, match="access_token"):
        opensky.fetch(keyed_ctx)

    respx.post(opensky.TOKEN_URL).mock(return_value=httpx.Response(401, text="bad creds"))
    with pytest.raises(httpx.HTTPStatusError):
        opensky.fetch(keyed_ctx)


def test_fetch_requires_credentials(ctx):
    opensky._reset_token_cache()
    with pytest.raises(ValueError, match="OPENSKY_CLIENT_ID"):
        opensky.fetch(ctx)

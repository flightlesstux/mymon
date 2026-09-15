from datetime import UTC, datetime

import httpx
import respx

from mymon_collector.sources import earthquakes_afad as mod
from tests.conftest import fixture_json

PK = {"id"}
URL_RE = r"https://deprem\.afad\.gov\.tr/apiv2/event/filter\?.*"


@respx.mock
def test_fetch(ctx):
    route = respx.get(url__regex=URL_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("earthquakes_afad_filter.json"))
    )
    out = mod.fetch(ctx)
    assert [t for t, _ in out] == ["earthquake"]
    rows = out[0][1]
    assert len(rows) == 4
    first = rows[0]
    assert first["id"] == "afad:728727"
    assert first["ts"] == datetime(2026, 9, 15, 17, 54, 47, tzinfo=UTC)
    assert first["lat"] == 37.976
    assert first["lon"] == 27.14
    assert first["depth_km"] == 6.94
    assert first["mag"] == 1.9
    assert first["place"].startswith("Ege Denizi")
    assert first["source"] == "afad"
    assert rows[3]["mag"] == 1.0
    assert all(PK <= r.keys() for r in rows)
    assert len({frozenset(r) for r in rows}) == 1
    params = route.calls.last.request.url.params
    assert params["start"] == "2026-09-14 12:00:00"
    assert params["end"] == "2026-09-15 12:00:00"
    assert params["minmag"] == "1.0"
    assert params["orderby"] == "timedesc"


@respx.mock
def test_backfill_chunks_by_month(ctx):
    route = respx.get(url__regex=URL_RE).mock(
        return_value=httpx.Response(200, json=fixture_json("earthquakes_afad_filter.json")[:2])
    )
    out = mod.backfill(ctx)
    assert [t for t, _ in out] == ["earthquake"]
    rows = out[0][1]
    assert route.call_count == 13  # 365 days in 30-day chunks
    assert len(rows) == 2 * 13
    assert all(PK <= r.keys() for r in rows)
    first_call = route.calls[0].request.url.params
    assert first_call["start"] == "2025-09-15 12:00:00"
    assert first_call["minmag"] == "3.0"
    assert route.calls.last.request.url.params["end"] == "2026-09-15 12:00:00"


@respx.mock
def test_skips_bad_records(ctx):
    payload = fixture_json("earthquakes_afad_filter.json")
    payload.append({"eventID": "x", "date": "not-a-date", "latitude": "1", "longitude": "2"})
    payload.append({"eventID": "y", "date": "2026-09-15T00:00:00", "latitude": None})
    payload.append("garbage")
    respx.get(url__regex=URL_RE).mock(return_value=httpx.Response(200, json=payload))
    rows = mod.fetch(ctx)[0][1]
    assert len(rows) == 4

from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from mymon_collector.sources import ns_public as ns

DISRUPTIONS_PAYLOAD = [
    {"id": "1", "type": "STORING", "isActive": True, "title": "Signal failure Utrecht"},
    {"id": "2", "type": "STORING", "isActive": True, "title": "Broken rail near Gouda"},
    {"id": "3", "type": "WERKZAAMHEDEN", "isActive": True, "title": "Weekend engineering works"},
    {"id": "4", "type": "STORING", "isActive": False, "title": "Resolved yesterday"},
    {"id": "5", "type": "WERKZAAMHEDEN", "title": "No isActive field, counted as active"},
]


def test_parse_disruptions_counts_active_by_type():
    total, unplanned = ns.parse_disruptions(DISRUPTIONS_PAYLOAD)
    assert total == 4  # entries 1, 2, 3, 5 (entry 4 is inactive)
    assert unplanned == 2  # entries 1, 2 (STORING and active)


def test_parse_disruptions_rejects_non_list():
    with pytest.raises(ValueError, match="not a list"):
        ns.parse_disruptions({"not": "a list"})


@respx.mock
def test_fetch_requires_api_key():
    ctx = _ctx(env={})
    with pytest.raises(RuntimeError, match="NS_API_KEY"):
        ns.fetch(ctx)


@respx.mock
def test_fetch_sends_subscription_key_header_and_upserts_counts():
    route = respx.get(
        "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/disruptions"
    ).mock(return_value=httpx.Response(200, json=DISRUPTIONS_PAYLOAD))

    ctx = _ctx(env={"NS_API_KEY": "test-key-123"})
    result = ns.fetch(ctx)

    assert route.called
    sent_headers = route.calls[0].request.headers
    assert sent_headers["Ocp-Apim-Subscription-Key"] == "test-key-123"

    table, rows = result[0]
    assert table == "price_index"
    by_indicator = {r["indicator"]: r["value"] for r in rows}
    assert by_indicator["ns_disruptions_active"] == 4.0
    assert by_indicator["ns_disruptions_unplanned"] == 2.0
    assert all(r["country_iso3"] == "NLD" and r["source"] == "ns" for r in rows)
    assert all(r["period_date"] == date(2026, 9, 16) for r in rows)


def _ctx(env: dict):
    return ns.Ctx(http=httpx.Client(), cfg={"cities": [], "env": env},
                  now=datetime(2026, 9, 16, 12, 0, tzinfo=UTC))

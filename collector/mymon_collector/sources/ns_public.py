"""NS (Nederlandse Spoorwegen, Dutch Railways) — active service disruptions.

The NS Reisinformatie API needs a free self-service API key (apiportal.ns.nl, instant
signup, no cost) — there is no keyless endpoint. Confirmed live (2026-09): a request
without a key gets ``401 Access denied due to invalid subscription key`` from the correct
route, ``reisinformatie-api/api/v3/disruptions``, so the path is right; only a real
``Ocp-Apim-Subscription-Key`` is missing here. Gated by ``requires_env`` like ``opensky.py``
— the registry disables this source until ``NS_API_KEY`` is set in ``.env``.

The API only reports *current* disruptions, no historical query, so — like ISS position or
mempool fees — this can only be collected going forward from whenever the key is added; it
cannot be backfilled to 2025.

Stored in ``price_index`` (``country_iso3='NLD'``, ``source='ns'``) as a simple count so it
fits straight into the existing NL dashboards: total active disruptions, split into
``ns_disruptions_active`` (all) and ``ns_disruptions_unplanned`` (type ``STORING``, i.e.
unplanned incidents, as opposed to planned engineering works).
"""

from __future__ import annotations

import logging
from datetime import UTC, date
from typing import Any

from ..source import Ctx, Rows, Source

log = logging.getLogger(__name__)

DISRUPTIONS_URL = "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/disruptions"
TABLE = "price_index"


def _today(ctx: Ctx) -> date:
    return ctx.now.astimezone(UTC).date()


def parse_disruptions(payload: Any) -> tuple[int, int]:
    """Returns (total active, unplanned/STORING active) from the v3 disruptions payload.

    Each entry has a ``type`` (``STORING`` unplanned incident, or ``WERKZAAMHEDEN`` planned
    engineering work) and an ``isActive`` flag; some deployments omit ``isActive`` and just
    list currently-active disruptions, so entries missing the flag are counted as active.
    """
    if not isinstance(payload, list):
        raise ValueError("NS disruptions: response is not a list")
    total = 0
    unplanned = 0
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("isActive") is False:
            continue
        total += 1
        if str(entry.get("type", "")).upper() == "STORING":
            unplanned += 1
    return total, unplanned


def fetch(ctx: Ctx) -> Rows:
    api_key = ctx.env("NS_API_KEY")
    if not api_key:
        raise RuntimeError("ns_public: NS_API_KEY not set")
    resp = ctx.http.get(
        DISRUPTIONS_URL,
        params={"isActive": "true"},
        headers={"Ocp-Apim-Subscription-Key": api_key},
    )
    resp.raise_for_status()
    total, unplanned = parse_disruptions(resp.json())
    today = _today(ctx)
    rows = [
        {"period_date": today, "country_iso3": "NLD", "indicator": "ns_disruptions_active",
         "value": float(total), "unit": "count", "source": "ns"},
        {"period_date": today, "country_iso3": "NLD", "indicator": "ns_disruptions_unplanned",
         "value": float(unplanned), "unit": "count", "source": "ns"},
    ]
    return [(TABLE, rows)]


SOURCE = Source(
    name="ns_public",
    interval=900,
    fetch=fetch,
    backfill=None,
    requires_env=["NS_API_KEY"],
    tables=[TABLE],
    description="NS active train disruption count (needs a free NS_API_KEY, live-only).",
)

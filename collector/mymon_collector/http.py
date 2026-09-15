"""Shared httpx client with retries, timeout and a descriptive User-Agent."""

from __future__ import annotations

import httpx

USER_AGENT = "mymon-collector/0.1 (+https://github.com/flightlesstux/mymon)"


def make_client(timeout: float = 30.0, retries: int = 3) -> httpx.Client:
    transport = httpx.HTTPTransport(retries=retries)
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=10.0),
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        transport=transport,
        follow_redirects=True,
    )

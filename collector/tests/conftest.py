from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

from mymon_collector.source import Ctx

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).parent.parent / "config"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_json(name: str):
    return json.loads(fixture_text(name))


@pytest.fixture
def cities() -> list[dict]:
    with (CONFIG / "cities.yml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["cities"]


@pytest.fixture
def ctx(cities) -> Ctx:
    with httpx.Client() as client:
        yield Ctx(
            http=client,
            cfg={"cities": cities, "env": {}},
            now=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        )

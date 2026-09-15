"""Contract every data source module implements.

A source module lives in ``mymon_collector/sources/<name>.py`` and exposes a module-level
``SOURCE = Source(...)``. ``fetch`` (and optional ``backfill``) receive a :class:`Ctx` and
return ``[(table_name, [row_dict, ...]), ...]``. Rows are upserted by the scheduler using
the table's primary key, so returning the same row twice is harmless.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

Rows = list[tuple[str, list[dict[str, Any]]]]


@dataclass
class Ctx:
    http: httpx.Client
    cfg: dict[str, Any]
    now: datetime

    @property
    def cities(self) -> list[dict[str, Any]]:
        return self.cfg.get("cities", [])

    def env(self, name: str, default: str | None = None) -> str | None:
        return self.cfg.get("env", {}).get(name, default)


FetchFn = Callable[[Ctx], Rows]


@dataclass
class Source:
    name: str
    interval: int  # seconds between runs
    fetch: FetchFn
    backfill: FetchFn | None = None
    requires_env: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)  # checked for emptiness before backfill
    description: str = ""

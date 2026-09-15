"""Discovers source modules and applies config/sources.yml overrides."""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from . import sources as sources_pkg
from .source import Source

log = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config"
CONFIG_DIR = Path(os.environ.get("MYMON_CONFIG_DIR", _DEFAULT_CONFIG))


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def discover() -> list[Source]:
    found: list[Source] = []
    for mod in pkgutil.iter_modules(sources_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        module = importlib.import_module(f"{sources_pkg.__name__}.{mod.name}")
        src = getattr(module, "SOURCE", None)
        if isinstance(src, Source):
            found.append(src)
        else:
            log.warning("module %s has no SOURCE, skipped", mod.name)
    return found


def apply_config(
    sources: list[Source],
    overrides: dict[str, Any],
    env: dict[str, str] | None = None,
) -> list[Source]:
    env = os.environ if env is None else env
    enabled: list[Source] = []
    for src in sources:
        cfg = overrides.get(src.name, {}) or {}
        if cfg.get("enabled", True) is False:
            log.info("source %s disabled by config", src.name)
            continue
        missing = [k for k in src.requires_env if not env.get(k)]
        if missing:
            log.warning("source %s disabled: missing env %s", src.name, ", ".join(missing))
            continue
        if "interval" in cfg:
            src = replace(src, interval=int(cfg["interval"]))
        enabled.append(src)
    return enabled


def load_sources() -> list[Source]:
    overrides = load_yaml("sources.yml").get("sources", {}) or {}
    return apply_config(discover(), overrides)


def load_ctx_config() -> dict[str, Any]:
    cities = load_yaml("cities.yml").get("cities", [])
    return {"cities": cities, "env": dict(os.environ)}

#!/usr/bin/env python3
"""Regenerate every dashboard JSON in grafana/dashboards/ from the scripts in this directory.

Run via `make dashboards`. Each sibling script builds one dashboard and calls `write()`
from `_lib.py` when executed. Adding a new dashboard = adding a new script here; nothing
else needs wiring.
"""

from __future__ import annotations

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP = {"_lib.py", "generate_all.py"}


def main() -> None:
    scripts = sorted(p for p in HERE.glob("*.py") if p.name not in SKIP)
    if not scripts:
        raise SystemExit("no dashboard scripts found next to generate_all.py")
    for script in scripts:
        runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()

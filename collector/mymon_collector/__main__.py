"""Entry point: ``python -m mymon_collector``."""

from __future__ import annotations

import logging
import os
import sys

from . import registry, scheduler


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("MYMON_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    log = logging.getLogger("mymon")

    sources = registry.load_sources()
    if not sources:
        log.error("no sources enabled, exiting")
        return 1
    cfg = registry.load_ctx_config()
    log.info("registered %d sources: %s", len(sources), ", ".join(s.name for s in sources))

    sched = scheduler.build(sources, cfg)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

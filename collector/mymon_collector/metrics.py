"""Prometheus metrics for the collector process itself.

This is operational telemetry (is each source running, how long does it take, is it
failing) — separate from the business data the sources write to Postgres. Scraped by
the `prometheus` service and kept as time series so we can see collector health history,
not just the latest row in `collector_run`.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

REGISTRY = CollectorRegistry()

RUN_TOTAL = Counter(
    "mymon_collector_run_total",
    "Number of times a source's fetch/backfill cycle ran, by outcome.",
    ["source", "outcome"],  # outcome: ok | error
    registry=REGISTRY,
)

ROWS_WRITTEN = Counter(
    "mymon_collector_rows_written_total",
    "Rows upserted by a source, cumulative.",
    ["source"],
    registry=REGISTRY,
)

RUN_DURATION = Histogram(
    "mymon_collector_run_duration_seconds",
    "Wall-clock time of one source run.",
    ["source"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    registry=REGISTRY,
)

SOURCE_UP = Gauge(
    "mymon_collector_source_up",
    "1 if the source's most recent run succeeded, 0 if it failed.",
    ["source"],
    registry=REGISTRY,
)

LAST_SUCCESS_TIMESTAMP = Gauge(
    "mymon_collector_source_last_success_timestamp_seconds",
    "Unix time of the source's last successful run.",
    ["source"],
    registry=REGISTRY,
)

SOURCES_REGISTERED = Gauge(
    "mymon_collector_sources_registered",
    "Number of sources currently scheduled.",
    registry=REGISTRY,
)


def record_run(source: str, ok: bool, duration_s: float, rows: int, finished_epoch: float) -> None:
    RUN_TOTAL.labels(source=source, outcome="ok" if ok else "error").inc()
    RUN_DURATION.labels(source=source).observe(duration_s)
    SOURCE_UP.labels(source=source).set(1 if ok else 0)
    if rows:
        ROWS_WRITTEN.labels(source=source).inc(rows)
    if ok:
        LAST_SUCCESS_TIMESTAMP.labels(source=source).set(finished_epoch)


def serve(port: int = 9200) -> None:
    start_http_server(port, registry=REGISTRY)

from _lib import CAT, PROM_DS, STATUS, dashboard, prom_target, stat, table, timeseries, write

LAST_RUNS = """
SELECT DISTINCT ON (source)
  source AS "Source",
  started_at AS "Last run",
  CASE WHEN ok THEN 'ok' ELSE 'error' END AS "Status",
  rows AS "Rows",
  round(extract(epoch FROM (finished_at - started_at))::numeric, 1) AS "Seconds",
  error AS "Error"
FROM collector_run
ORDER BY source, started_at DESC
"""

ROWS_PER_HOUR = """
SELECT $__timeGroupAlias(started_at, '1h'), source AS metric, sum(rows) AS value
FROM collector_run
WHERE $__timeFilter(started_at) AND ok
GROUP BY 1, 2 ORDER BY 1
"""

FAILURES = """
SELECT $__timeGroupAlias(started_at, '1h'), count(*) AS "failures"
FROM collector_run
WHERE $__timeFilter(started_at) AND NOT ok
GROUP BY 1 ORDER BY 1
"""

TOTAL_ROWS = """
SELECT sum(rows) AS "rows" FROM collector_run WHERE ok AND started_at > now() - interval '24 hours'
"""

SOURCES_OK = """
SELECT count(*) FILTER (WHERE ok) AS "healthy"
FROM (SELECT DISTINCT ON (source) source, ok FROM collector_run ORDER BY source, started_at DESC) t
"""

SOURCES_ERR = """
SELECT count(*) FILTER (WHERE NOT ok) AS "failing"
FROM (SELECT DISTINCT ON (source) source, ok FROM collector_run ORDER BY source, started_at DESC) t
"""

status_override = [{
    "matcher": {"id": "byName", "options": "Status"},
    "properties": [
        {"id": "custom.cellOptions", "value": {"type": "color-text"}},
        {"id": "mappings", "value": [
            {"type": "value", "options": {"ok": {"color": STATUS["good"], "index": 0},
                                          "error": {"color": STATUS["critical"], "index": 1}}}]},
    ],
}, {
    "matcher": {"id": "byName", "options": "Last run"},
    "properties": [{"id": "unit", "value": "dateTimeAsIso"}],
}]

panels = [
    stat("Healthy sources", 0, 0, 6, 4, SOURCES_OK, color=STATUS["good"], sparkline=False),
    stat("Failing sources", 6, 0, 6, 4, SOURCES_ERR, sparkline=False,
         thresholds=[{"color": STATUS["good"], "value": None}, {"color": STATUS["critical"], "value": 1}]),
    stat("Rows written, 24 h", 12, 0, 12, 4, TOTAL_ROWS, unit="short", sparkline=False, color=CAT[0]),
    table("Last run per source", 0, 4, 24, 11, LAST_RUNS, overrides=status_override, sort=("Source", False)),
    timeseries("Rows written per hour by source", 0, 15, 14, 9, ROWS_PER_HOUR, unit="short", stack=True, fill=60, lw=1),
    timeseries("Failed runs per hour", 14, 15, 10, 9, FAILURES, unit="short",
               colors={"failures": STATUS["critical"]}, fill=40),

    # Prometheus scrapes the collector's own /metrics and postgres-exporter every 30s and
    # keeps 90 days of history, so these panels answer "how has this looked over time" —
    # collector_run in Postgres above only ever shows the current run per source.
    stat("Sources registered", 0, 24, 4, 4, targets=[prom_target("mymon_collector_sources_registered")],
         datasource=PROM_DS, color=CAT[0], sparkline=False),
    stat("Postgres up", 4, 24, 4, 4, targets=[prom_target("pg_up")], datasource=PROM_DS, sparkline=False,
         thresholds=[{"color": STATUS["critical"], "value": None}, {"color": STATUS["good"], "value": 1}]),
    stat("Postgres connections", 8, 24, 4, 4,
         targets=[prom_target('pg_stat_database_numbackends{datname="mymon"}')], datasource=PROM_DS,
         color=CAT[2], sparkline=True),
    stat("Database size", 12, 24, 4, 4, targets=[prom_target('pg_database_size_bytes{datname="mymon"}')],
         datasource=PROM_DS, unit="bytes", decimals=1, color=CAT[6], sparkline=True),
    stat("Postgres commits / s", 16, 24, 8, 4,
         targets=[prom_target('rate(pg_stat_database_xact_commit{datname="mymon"}[5m])')],
         datasource=PROM_DS, decimals=1, color=CAT[3], sparkline=True),

    timeseries("Average run duration by source (Prometheus)", 0, 28, 12, 9,
               targets=[prom_target(
                   "rate(mymon_collector_run_duration_seconds_sum[15m])"
                   " / rate(mymon_collector_run_duration_seconds_count[15m])",
                   legend="{{source}}")],
               datasource=PROM_DS, unit="s", decimals=2, fill=0, legend="right",
               description="Histogram average over a 15-minute window, per source."),
    timeseries("Rows written per minute by source (Prometheus)", 12, 28, 12, 9,
               targets=[prom_target("rate(mymon_collector_rows_written_total[15m]) * 60",
                                     legend="{{source}}")],
               datasource=PROM_DS, unit="short", decimals=1, fill=0, legend="right"),
]

write(dashboard("collector-health", "Collector Health", panels, ["mymon", "ops"],
                refresh="1m", time_from="now-24h",
                description="What the collector has been doing: last result per source, rows written, failures."),
      "collector-health")

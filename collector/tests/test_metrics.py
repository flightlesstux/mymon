from prometheus_client import generate_latest

from mymon_collector import metrics


def test_record_run_ok_updates_all_series():
    metrics.record_run("weather", True, 1.5, 42, 1_700_000_000.0)
    body = generate_latest(metrics.REGISTRY).decode()
    assert 'mymon_collector_run_total{outcome="ok",source="weather"} 1.0' in body
    assert 'mymon_collector_source_up{source="weather"} 1.0' in body
    assert "mymon_collector_source_last_success_timestamp_seconds" in body
    assert "mymon_collector_rows_written_total" in body


def test_record_run_error_sets_source_down():
    metrics.record_run("crypto", False, 0.2, 0, 1_700_000_100.0)
    body = generate_latest(metrics.REGISTRY).decode()
    assert 'mymon_collector_source_up{source="crypto"} 0.0' in body
    assert 'mymon_collector_run_total{outcome="error",source="crypto"} 1.0' in body


def test_sources_registered_gauge():
    metrics.SOURCES_REGISTERED.set(23)
    body = generate_latest(metrics.REGISTRY).decode()
    assert "mymon_collector_sources_registered 23.0" in body

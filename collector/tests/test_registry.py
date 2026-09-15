from mymon_collector.registry import apply_config
from mymon_collector.source import Source


def _src(name, **kw):
    return Source(name=name, interval=60, fetch=lambda ctx: [], **kw)


def test_disabled_by_config():
    out = apply_config([_src("a"), _src("b")], {"a": {"enabled": False}}, env={})
    assert [s.name for s in out] == ["b"]


def test_interval_override():
    out = apply_config([_src("a")], {"a": {"interval": 5}}, env={})
    assert out[0].interval == 5


def test_missing_env_disables():
    out = apply_config([_src("a", requires_env=["KEY"])], {}, env={})
    assert out == []
    out = apply_config([_src("a", requires_env=["KEY"])], {}, env={"KEY": "x"})
    assert len(out) == 1

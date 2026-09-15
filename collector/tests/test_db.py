from mymon_collector.db import build_upsert


class FakeConn:
    """Minimal psycopg-like connection so sql.Composed.as_string works without a server."""

    def __init__(self):
        self.info = None


def render(composed) -> str:
    # psycopg's Composed.as_string needs a connection for quoting; Identifier/Placeholder
    # render deterministically with None context in psycopg>=3.2.
    return composed.as_string(None)


def test_upsert_updates_non_pk_columns():
    stmt = render(build_upsert("fx_rate", ["ts", "base", "quote", "rate", "source"],
                               ["ts", "base", "quote", "source"]))
    assert stmt.startswith('INSERT INTO "fx_rate" ("ts", "base", "quote", "rate", "source")')
    expected = (
        'ON CONFLICT ("ts", "base", "quote", "source") '
        'DO UPDATE SET "rate" = EXCLUDED."rate"'
    )
    assert expected in stmt
    assert "%(rate)s" in stmt


def test_upsert_all_pk_does_nothing():
    stmt = render(build_upsert("t", ["a", "b"], ["a", "b"]))
    assert stmt.endswith("DO NOTHING")

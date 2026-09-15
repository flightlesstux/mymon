from mymon_collector.retention import POLICY, delete_statement


def test_delete_statement_renders():
    stmt = delete_statement("crypto_tick", "ts", "90 days").as_string(None)
    assert stmt == 'DELETE FROM "crypto_tick" WHERE "ts" < now() - interval \'90 days\''


def test_policy_covers_tick_tables():
    assert {"crypto_tick", "iss_position"} <= set(POLICY)

from datetime import datetime, timezone
import unittest

from continuum.store import (
    CockroachMemoryStore,
    PsycopgConnectionPool,
    TransactionRetryExhaustedError,
    database_url_user,
    pin_database_tls_root,
)


class FakePool:
    def __init__(self, **settings):
        self.settings = settings
        self.open_calls = []
        self.connection_calls = []
        self.close_calls = []

    def open(self, **settings):
        self.open_calls.append(settings)

    def connection(self, **settings):
        self.connection_calls.append(settings)
        return "pooled-connection-context"

    def close(self, **settings):
        self.close_calls.append(settings)

    def get_stats(self):
        return {"pool_size": 4, "requests_waiting": 0}


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


class DatabaseTlsTests(unittest.TestCase):
    def test_database_user_decodes_without_returning_password(self):
        result = database_url_user(
            "postgresql://continuum%5Fscope:do-not-return@example/continuum"
        )

        self.assertEqual(result, "continuum_scope")

    def test_private_ca_replaces_untrusted_query_values(self):
        result = pin_database_tls_root(
            "postgresql://user:secret@db.example:26257/app"
            "?sslmode=require&sslrootcert=%2Fwrong%2Fca.crt&application_name=demo",
            "/opt/continuum/cockroach-ca.crt",
        )

        self.assertIn("sslmode=verify-full", result)
        self.assertIn("sslrootcert=%2Fopt%2Fcontinuum%2Fcockroach-ca.crt", result)
        self.assertIn("application_name=demo", result)
        self.assertNotIn("wrong", result)


class ConnectionPoolTests(unittest.TestCase):
    def test_pool_opens_once_and_returns_bounded_borrow_contexts(self):
        pools = []

        def factory(**settings):
            pool = FakePool(**settings)
            pools.append(pool)
            return pool

        connect = PsycopgConnectionPool(
            "postgresql://user:never-log@example.test/app",
            min_size=1,
            max_size=4,
            timeout_seconds=3,
            pool_factory=factory,
        )
        self.assertEqual(connect(), "pooled-connection-context")
        self.assertEqual(connect(), "pooled-connection-context")
        self.assertEqual(pools[0].open_calls, [{"wait": True, "timeout": 3}])
        self.assertEqual(
            pools[0].connection_calls,
            [{"timeout": 3}, {"timeout": 3}],
        )
        self.assertEqual(connect.metrics(), {"pool_size": 4, "requests_waiting": 0})
        self.assertNotIn("never-log", str(connect.metrics()))
        connect.close()
        self.assertEqual(pools[0].close_calls, [{"timeout": 3}])

    def test_pool_rejects_unbounded_or_invalid_settings(self):
        with self.assertRaises(ValueError):
            PsycopgConnectionPool("postgresql://example", min_size=2, max_size=1)


class RetryableError(Exception):
    sqlstate = "40001"


class Transaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class Connection:
    def __init__(self, *, fail=False):
        self.fail = fail

    def __enter__(self):
        if self.fail:
            raise RetryableError("restart transaction")
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def transaction(self):
        return Transaction()


class StoreRetryTests(unittest.TestCase):
    def test_retries_serialization_failure(self):
        calls = 0
        sleeps = []

        def connect():
            nonlocal calls
            calls += 1
            return Connection(fail=calls < 3)

        store = CockroachMemoryStore(connect, sleep=sleeps.append)
        result = store._run_transaction(lambda connection: "committed")

        self.assertEqual(result, "committed")
        self.assertEqual(calls, 3)
        self.assertEqual(sleeps, [0.01, 0.02])

    def test_does_not_retry_non_serialization_error(self):
        class FatalConnection(Connection):
            def __enter__(self):
                raise ValueError("invalid query")

        store = CockroachMemoryStore(FatalConnection, sleep=lambda _: None)

        with self.assertRaisesRegex(ValueError, "invalid query"):
            store._run_transaction(lambda connection: None)

    def test_raises_after_retry_budget_is_exhausted(self):
        store = CockroachMemoryStore(
            lambda: Connection(fail=True),
            max_attempts=2,
            sleep=lambda _: None,
        )

        with self.assertRaises(TransactionRetryExhaustedError):
            store._run_transaction(lambda connection: None)


if __name__ == "__main__":
    unittest.main()

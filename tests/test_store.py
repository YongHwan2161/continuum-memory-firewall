from datetime import datetime, timezone
import unittest

from continuum.store import (
    CockroachMemoryStore,
    TransactionRetryExhaustedError,
)


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


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

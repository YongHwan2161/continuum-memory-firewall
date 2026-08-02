import unittest

from continuum.identity import CallerIdentity
from continuum.judge_story import (
    CachedJudgeStoryEndpoint,
    JudgeStoryService,
    STORY_ID,
    STORY_MEMORY_KEY,
    STORY_TITLE,
)
from continuum.mcp_server import FetchOutput, SearchOutput, SearchResult


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, parameters=()):
        if "JOIN canonical_memories" in sql:
            self.accepted_parameter = parameters
            return _Result(("candidate-ok", "ACCEPTED", "memory-1", 7, "titan-v2"))
        if "FROM memory_candidates" in sql:
            return _Result(("candidate-bad", "UNTRUSTED_SOURCE"))
        if "FROM action_attempts" in sql:
            return _Result(("attempt-1", "agent-a", "approved", "f" * 64, 1))
        if "FROM retrieval_audit" in sql:
            return _Result(("audit-1", "titan-v2", 3, 1))
        raise AssertionError(sql)


class _Knowledge:
    def search(self, _query):
        return SearchOutput(
            results=[
                SearchResult(
                    id="memory-1",
                    title=STORY_TITLE,
                    url="https://example.test/?memory=memory-1",
                )
            ]
        )

    def fetch(self, memory_id):
        return FetchOutput(
            id=memory_id,
            title=STORY_TITLE,
            text='{"synthetic":true}',
            url="https://example.test/?memory=memory-1",
            metadata={"sequence_no": 7},
        )


class JudgeStoryTests(unittest.TestCase):
    def service(self):
        self.connection = _Connection()
        return JudgeStoryService(
            _Knowledge(),
            CallerIdentity(
                "judge-caller",
                "tenant-a",
                "incident-a",
                "continuum_scope_abc",
                2,
            ),
            lambda: self.connection,
        )

    def test_live_story_binds_all_four_receipts(self):
        result = self.service().run(STORY_ID)
        self.assertTrue(result["live"])
        self.assertEqual(result["storage"]["decision"], "ACCEPTED")
        self.assertEqual(result["poisoning"]["decision"], "UNTRUSTED_SOURCE")
        self.assertEqual(result["retrieval"]["audit_id"], "audit-1")
        self.assertEqual(result["action"]["durable_claim_count"], 1)
        self.assertEqual(result["action"]["worker_b"], "DUPLICATE")
        self.assertEqual(self.connection.accepted_parameter, (STORY_MEMORY_KEY,))

    def test_unknown_story_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown judge scenario"):
            self.service().run("free-form-input")

    def test_endpoint_reuses_short_lived_receipt(self):
        calls = []

        class Service:
            def run(self, scenario):
                calls.append(scenario)
                return {"ok": True, "scenario": scenario}

        times = iter((100.0, 101.0, 140.0))
        endpoint = CachedJudgeStoryEndpoint(
            Service(), ttl_seconds=30, clock=lambda: next(times)
        )
        first, first_cached = endpoint.run(STORY_ID)
        second, second_cached = endpoint.run(STORY_ID)
        third, third_cached = endpoint.run(STORY_ID)
        self.assertIs(first, second)
        self.assertFalse(first_cached)
        self.assertTrue(second_cached)
        self.assertFalse(third_cached)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()

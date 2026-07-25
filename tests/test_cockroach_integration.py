from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import unittest

from continuum.memory import DecisionCode
from continuum.store import (
    ActionClaimCode,
    CockroachMemoryStore,
    psycopg_connection_factory,
)


DATABASE_URL = os.environ.get("CONTINUUM_DATABASE_URL")
NOW = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
TENANT_ID = "11111111-1111-4111-8111-111111111111"
INCIDENT_ID = "22222222-2222-4222-8222-222222222222"
CANDIDATE_ID = "33333333-3333-4333-8333-333333333333"
STALE_CANDIDATE_ID = "44444444-4444-4444-8444-444444444444"
INITIAL_HEAD = "0" * 64


@unittest.skipUnless(DATABASE_URL, "CONTINUUM_DATABASE_URL is not configured")
class CockroachIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect = staticmethod(psycopg_connection_factory(DATABASE_URL))
        schema = (
            Path(__file__).parents[1] / "db" / "schema.sql"
        ).read_text(encoding="utf-8")
        with cls.connect() as connection:
            connection.autocommit = True
            connection.execute(
                "SET CLUSTER SETTING feature.vector_index.enabled = true"
            )
            connection.execute(schema)

    def setUp(self):
        with self.connect() as connection:
            connection.execute(
                """
                TRUNCATE TABLE
                    retrieval_audit,
                    action_attempts,
                    canonical_memories,
                    memory_candidates,
                    incidents
                CASCADE
                """
            )
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id, tenant_id, service_name, status, current_head
                )
                VALUES (%s, %s, 'checkout', 'open', %s)
                """,
                (INCIDENT_ID, TENANT_ID, INITIAL_HEAD),
            )
        self._insert_candidate(CANDIDATE_ID, INITIAL_HEAD)
        self.store = CockroachMemoryStore(self.connect, sleep=lambda _: None)

    def _insert_candidate(self, candidate_id, parent_hash):
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_candidates (
                    candidate_id,
                    tenant_id,
                    incident_id,
                    parent_hash,
                    source_kind,
                    action_class,
                    payload,
                    created_at,
                    expires_at
                )
                VALUES (%s, %s, %s, %s, 'tool', 'observe', %s::JSONB, %s, %s)
                """,
                (
                    candidate_id,
                    TENANT_ID,
                    INCIDENT_ID,
                    parent_hash,
                    json.dumps({"service": "checkout", "error_rate": 0.21}),
                    NOW - timedelta(seconds=1),
                    NOW + timedelta(minutes=10),
                ),
            )

    def test_promotion_is_durable_and_idempotent(self):
        first = self.store.promote_candidate(CANDIDATE_ID, now=NOW)
        replay = self.store.promote_candidate(CANDIDATE_ID, now=NOW)

        self.assertEqual(first.decision_code, DecisionCode.ACCEPTED)
        self.assertEqual(first.sequence_no, 1)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.event_hash, first.event_hash)
        self.assertEqual(replay.memory_id, first.memory_id)
        with self.connect() as connection:
            count = connection.execute(
                "SELECT count(*) FROM canonical_memories"
            ).fetchone()[0]
            head = connection.execute(
                "SELECT current_head FROM incidents WHERE incident_id = %s",
                (INCIDENT_ID,),
            ).fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(head, first.event_hash)

    def test_stale_candidate_is_rejected_and_auditable(self):
        self._insert_candidate(STALE_CANDIDATE_ID, "f" * 64)

        result = self.store.promote_candidate(STALE_CANDIDATE_ID, now=NOW)

        self.assertEqual(result.decision_code, DecisionCode.STALE_PARENT)
        with self.connect() as connection:
            decision = connection.execute(
                """
                SELECT decision_code
                FROM memory_candidates
                WHERE candidate_id = %s
                """,
                (STALE_CANDIDATE_ID,),
            ).fetchone()[0]
        self.assertEqual(decision, DecisionCode.STALE_PARENT.value)

    def test_concurrent_workers_produce_one_action_claim(self):
        promoted = self.store.promote_candidate(CANDIDATE_ID, now=NOW)

        def claim(worker_id):
            return self.store.claim_action(
                tenant_id=TENANT_ID,
                incident_id=INCIDENT_ID,
                expected_head=promoted.event_hash,
                action_key="restart-checkout-v1",
                action_payload={"deployment": "checkout"},
                worker_id=worker_id,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ("worker-a", "worker-b")))

        self.assertEqual(
            {result.code for result in results},
            {ActionClaimCode.CLAIMED, ActionClaimCode.DUPLICATE},
        )
        self.assertEqual(results[0].attempt_id, results[1].attempt_id)
        with self.connect() as connection:
            count = connection.execute(
                "SELECT count(*) FROM action_attempts"
            ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()

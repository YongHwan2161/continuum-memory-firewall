from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

from continuum.db_smoke import run_smoke
from continuum.identity import IdentityVerificationError
from continuum.migrate import (
    MigrationDriftError,
    MigrationLockError,
    Migrator,
    discover_migrations,
)
from continuum.memory import DecisionCode
from continuum.retrieval import (
    HASH_EMBEDDING_MODEL,
    HashingEmbedder,
    MemoryNotFoundError,
    MemoryRetrievalStore,
)
from continuum.scope_roles import provision_scope_role, scope_role_name, verify_scope_role
from continuum.store import (
    ActionClaimCode,
    CockroachMemoryStore,
    psycopg_connection_factory,
)
from continuum.tenant_control import (
    CONTROL_PLANE_USER,
    DatabaseTenantControlPlane,
    bind_caller_scope,
    database_url_with_login,
    disable_caller,
    provision_control_plane_role,
    verify_control_plane_role,
)


DATABASE_URL = os.environ.get("CONTINUUM_DATABASE_URL")
NOW = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
TENANT_ID = "11111111-1111-4111-8111-111111111111"
INCIDENT_ID = "22222222-2222-4222-8222-222222222222"
CANDIDATE_ID = "33333333-3333-4333-8333-333333333333"
STALE_CANDIDATE_ID = "44444444-4444-4444-8444-444444444444"
SECOND_TENANT_ID = "55555555-5555-4555-8555-555555555555"
SECOND_INCIDENT_ID = "66666666-6666-4666-8666-666666666666"
SECOND_CANDIDATE_ID = "77777777-7777-4777-8777-777777777777"
INITIAL_HEAD = "0" * 64


@unittest.skipUnless(DATABASE_URL, "CONTINUUM_DATABASE_URL is not configured")
class CockroachIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect = staticmethod(psycopg_connection_factory(DATABASE_URL))
        with cls.connect() as connection:
            connection.autocommit = True
            connection.execute(
                "SET CLUSTER SETTING feature.vector_index.enabled = true"
            )
        cls.migrator = Migrator(cls.connect, sleep=lambda _: None)
        cls.initial_migration_report = cls.migrator.migrate()

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
        self.retrieval = MemoryRetrievalStore(
            self.connect,
            sleep=lambda _: None,
        )
        self.embedder = HashingEmbedder()

    def test_migrations_are_complete_and_idempotent(self):
        report = self.migrator.migrate()
        migrations = discover_migrations()

        self.assertEqual(report.applied, ())
        self.assertEqual(report.adopted, ())
        self.assertEqual(report.current_version, migrations[-1].version)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT version, name, checksum
                FROM continuum_schema_migrations
                ORDER BY version
                """
            ).fetchall()
        self.assertEqual(
            [(row[0], row[1]) for row in rows],
            [(item.version, item.name) for item in migrations],
        )
        self.assertEqual(
            [row[2] for row in rows],
            [item.checksum for item in migrations],
        )

    def test_live_database_smoke_round_trip_cleans_up(self):
        result = run_smoke(DATABASE_URL)

        self.assertTrue(result["ok"])
        self.assertFalse(result["retained"])
        self.assertEqual(result["migration"]["applied"], [])
        with self.connect() as connection:
            count = connection.execute(
                """
                SELECT count(*)
                FROM incidents
                WHERE incident_id = %s
                """,
                (result["incident_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_migration_checksum_drift_is_rejected(self):
        migrations = list(discover_migrations())
        migrations[0] = type(migrations[0])(
            version=migrations[0].version,
            name=migrations[0].name,
            checksum="0" * 64,
            sql=migrations[0].sql,
            path=migrations[0].path,
        )
        with self.assertRaises(MigrationDriftError):
            Migrator(
                self.connect,
                migrations=migrations,
                sleep=lambda _: None,
            ).migrate()

    def test_migration_lease_rejects_a_second_owner(self):
        with self.migrator.lease():
            with self.assertRaises(MigrationLockError):
                Migrator(
                    self.connect,
                    sleep=lambda _: None,
                ).migrate()

    def test_migration_resumes_after_ddl_before_history_crash(self):
        database_name = f"continuum_resume_{uuid4().hex}"
        parts = urlsplit(DATABASE_URL)
        database_url = urlunsplit(
            (parts.scheme, parts.netloc, f"/{database_name}", parts.query, "")
        )
        with self.connect() as connection:
            connection.autocommit = True
            connection.execute(f"CREATE DATABASE {database_name}")
        try:
            connect = psycopg_connection_factory(database_url)
            migrations = discover_migrations()
            interrupted = Migrator(connect, sleep=lambda _: None)
            interrupted._bootstrap_metadata()
            interrupted._start_intent(migrations[0])
            interrupted._execute_migration(migrations[0])

            report = Migrator(connect, sleep=lambda _: None).migrate()

            self.assertEqual(
                report.applied,
                tuple(item.version for item in migrations),
            )
            with connect() as connection:
                intents = connection.execute(
                    "SELECT count(*) FROM continuum_migration_intents"
                ).fetchone()[0]
                history = connection.execute(
                    "SELECT count(*) FROM continuum_schema_migrations"
                ).fetchone()[0]
            self.assertEqual(intents, 0)
            self.assertEqual(history, len(migrations))
        finally:
            with self.connect() as connection:
                connection.autocommit = True
                connection.execute(f"DROP DATABASE {database_name} CASCADE")

    def _insert_incident(
        self,
        *,
        tenant_id=TENANT_ID,
        incident_id=INCIDENT_ID,
        service_name="checkout",
    ):
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id, tenant_id, service_name, status, current_head
                )
                VALUES (%s, %s, %s, 'open', %s)
                """,
                (incident_id, tenant_id, service_name, INITIAL_HEAD),
            )

    def _insert_candidate(
        self,
        candidate_id,
        parent_hash,
        *,
        tenant_id=TENANT_ID,
        incident_id=INCIDENT_ID,
        payload=None,
    ):
        payload = payload or {"service": "checkout", "error_rate": 0.21}
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
                    tenant_id,
                    incident_id,
                    parent_hash,
                    json.dumps(payload),
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

    def test_vector_search_is_scoped_ranked_and_audited(self):
        promoted = self.store.promote_candidate(CANDIDATE_ID, now=NOW)
        self.retrieval.index_memory(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            memory_id=promoted.memory_id,
            embedder=self.embedder,
            now=NOW,
        )

        result = self.retrieval.search(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            query="checkout error",
            embedder=self.embedder,
            min_similarity=0.01,
        )

        self.assertEqual(result.evaluated_memory_ids, (promoted.memory_id,))
        self.assertEqual(
            [hit.memory_id for hit in result.hits],
            [promoted.memory_id],
        )
        self.assertEqual(result.embedding_model, HASH_EMBEDDING_MODEL)
        with self.connect() as connection:
            audit = connection.execute(
                """
                SELECT
                    tenant_id::STRING,
                    incident_id::STRING,
                    embedding_model,
                    returned_memory_ids,
                    accepted_memory_ids,
                    query_digest,
                    policy_digest
                FROM retrieval_audit
                WHERE retrieval_id = %s
                """,
                (result.retrieval_id,),
            ).fetchone()
        self.assertEqual(audit[0], TENANT_ID)
        self.assertEqual(audit[1], INCIDENT_ID)
        self.assertEqual(audit[2], HASH_EMBEDDING_MODEL)
        self.assertEqual([str(value) for value in audit[3]], [promoted.memory_id])
        self.assertEqual([str(value) for value in audit[4]], [promoted.memory_id])
        self.assertEqual(audit[5], result.query_digest)
        self.assertEqual(audit[6], result.policy_digest)

    def test_search_and_fetch_do_not_cross_tenant_scope(self):
        first = self.store.promote_candidate(CANDIDATE_ID, now=NOW)
        self.retrieval.index_memory(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            memory_id=first.memory_id,
            embedder=self.embedder,
            now=NOW,
        )
        self._insert_incident(
            tenant_id=SECOND_TENANT_ID,
            incident_id=SECOND_INCIDENT_ID,
            service_name="payments",
        )
        self._insert_candidate(
            SECOND_CANDIDATE_ID,
            INITIAL_HEAD,
            tenant_id=SECOND_TENANT_ID,
            incident_id=SECOND_INCIDENT_ID,
            payload={"service": "checkout", "error": "timeout"},
        )
        second = self.store.promote_candidate(SECOND_CANDIDATE_ID, now=NOW)
        self.retrieval.index_memory(
            tenant_id=SECOND_TENANT_ID,
            incident_id=SECOND_INCIDENT_ID,
            memory_id=second.memory_id,
            embedder=self.embedder,
            now=NOW,
        )

        result = self.retrieval.search(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            query="checkout timeout",
            embedder=self.embedder,
            min_similarity=-1.0,
        )

        self.assertEqual(result.evaluated_memory_ids, (first.memory_id,))
        with self.assertRaises(MemoryNotFoundError):
            self.retrieval.fetch_memory(
                tenant_id=TENANT_ID,
                incident_id=INCIDENT_ID,
                memory_id=second.memory_id,
            )

    def test_scope_login_cannot_bypass_database_row_policy(self):
        allowed = self.store.promote_candidate(CANDIDATE_ID, now=NOW)
        self.retrieval.index_memory(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            memory_id=allowed.memory_id,
            embedder=self.embedder,
            now=NOW,
        )
        self._insert_incident(
            tenant_id=SECOND_TENANT_ID,
            incident_id=SECOND_INCIDENT_ID,
            service_name="payments",
        )
        self._insert_candidate(
            SECOND_CANDIDATE_ID,
            INITIAL_HEAD,
            tenant_id=SECOND_TENANT_ID,
            incident_id=SECOND_INCIDENT_ID,
        )
        forbidden = self.store.promote_candidate(SECOND_CANDIDATE_ID, now=NOW)
        password = "scope-test-password-that-is-long-enough"
        provision_scope_role(
            DATABASE_URL,
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            password=password,
        )
        parts = urlsplit(DATABASE_URL)
        host = parts.hostname or "localhost"
        if ":" in host:
            host = f"[{host}]"
        netloc = (
            f"{quote(scope_role_name(TENANT_ID, INCIDENT_ID), safe='')}:"
            f"{quote(password, safe='')}@{host}"
        )
        if parts.port:
            netloc += f":{parts.port}"
        runtime_url = urlunsplit(
            (parts.scheme, netloc, parts.path, parts.query, "")
        )

        report = verify_scope_role(
            runtime_url,
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            forbidden_memory_id=forbidden.memory_id,
        )

        self.assertTrue(report["all_visible_rows_in_scope"])
        self.assertFalse(report["forbidden_memory_visible"])
        self.assertEqual(
            set(report["denied"]), {"row_security_off", "canonical_update"}
        )
        self.assertTrue(report["all_visible_incidents_in_scope"])
        self.assertTrue(report["all_visible_audits_in_scope"])
        self.assertEqual(report["visible_incidents"], 1)

        runtime_retrieval = MemoryRetrievalStore(
            psycopg_connection_factory(runtime_url)
        )
        search = runtime_retrieval.search(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            query="checkout timeout",
            embedder=self.embedder,
            min_similarity=-1.0,
        )
        self.assertIn(allowed.memory_id, search.evaluated_memory_ids)
        self.assertNotIn(forbidden.memory_id, search.evaluated_memory_ids)

    def test_audited_tenant_control_plane_binds_and_revokes_caller(self):
        password = "control-plane-test-password-that-is-long-enough"
        provision_control_plane_role(DATABASE_URL, password=password)
        control_url = database_url_with_login(
            DATABASE_URL,
            user=CONTROL_PLANE_USER,
            password=password,
        )
        bound = bind_caller_scope(
            DATABASE_URL,
            caller_id="integration-client",
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            actor="integration-test",
            reason="prove audited caller binding",
        )
        self.assertEqual(bound["binding_version"], 1)
        self.assertEqual(bound["event_type"], "bound")
        identity = DatabaseTenantControlPlane(
            psycopg_connection_factory(control_url)
        ).resolve("integration-client")
        self.assertEqual(identity.sql_role, scope_role_name(TENANT_ID, INCIDENT_ID))
        self.assertEqual(identity.binding_version, 1)
        privilege = verify_control_plane_role(control_url)
        self.assertTrue(privilege["canonical_memory_denied"])

        disabled = disable_caller(
            DATABASE_URL,
            caller_id="integration-client",
            actor="integration-test",
            reason="prove immediate revocation",
        )
        self.assertEqual(disabled["binding_version"], 2)
        with self.assertRaises(IdentityVerificationError):
            DatabaseTenantControlPlane(
                psycopg_connection_factory(control_url)
            ).resolve("integration-client")
        with self.connect() as connection:
            events = connection.execute(
                """
                SELECT event_type, binding_version
                FROM tenant_scope_binding_audit
                WHERE caller_id = 'integration-client'
                ORDER BY binding_version
                """
            ).fetchall()
        self.assertEqual(events, [("bound", 1), ("disabled", 2)])

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

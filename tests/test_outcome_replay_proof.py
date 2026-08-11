from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from continuum.episode import (
    OUTCOME_RECONCILIATION_GENESIS_HASH,
    OutcomeReplayIdentity,
    OutcomeStatus,
    build_outcome_reconciliation_entry,
)
from continuum.outcome_replay_proof import (
    PUBLIC_KIND,
    build_public_outcome_replay_proof,
    validate_outcome_replay_proof,
)
from scripts.judge_readonly_verify import verify_outcome_replay_cas
from scripts.promote_outcome_replay_cas_evidence import build_reference


def _entry_dict(entry):
    return {
        "reconciliation_id": entry.reconciliation_id,
        "proposal_id": entry.proposal_id,
        "outcome_id": entry.outcome_id,
        "run_id": entry.run_id,
        "tenant_id": entry.tenant_id,
        "incident_id": entry.incident_id,
        "decision": entry.decision,
        "incoming": {
            "provider": entry.incoming.provider,
            "status": entry.incoming.status.value,
            "provider_receipt_id": entry.incoming.provider_receipt_id,
            "receipt_digest": entry.incoming.receipt_digest,
        },
        "durable": {
            "provider": entry.durable.provider,
            "status": entry.durable.status.value,
            "provider_receipt_id": entry.durable.provider_receipt_id,
            "receipt_digest": entry.durable.receipt_digest,
        },
        "error_code": entry.error_code,
        "sequence_no": entry.sequence_no,
        "previous_entry_hash": entry.previous_entry_hash,
        "entry_hash": entry.entry_hash,
        "recorded_at": entry.recorded_at.isoformat(),
    }


def valid_report():
    identifiers = {
        "proposal_id": "11111111-1111-4111-8111-111111111111",
        "outcome_id": "22222222-2222-4222-8222-222222222222",
        "run_id": "33333333-3333-4333-8333-333333333333",
        "tenant_id": "44444444-4444-4444-8444-444444444444",
        "incident_id": "55555555-5555-4555-8555-555555555555",
    }
    accepted = OutcomeReplayIdentity(
        provider="aws-s3",
        status=OutcomeStatus.SUCCEEDED,
        provider_receipt_id="aws-s3:" + "a" * 64,
        receipt_digest="b" * 64,
    )
    conflicting = OutcomeReplayIdentity(
        provider="aws-s3",
        status=OutcomeStatus.SUCCEEDED,
        provider_receipt_id="aws-s3:" + "c" * 64,
        receipt_digest="d" * 64,
    )
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    entries = []
    previous = OUTCOME_RECONCILIATION_GENESIS_HASH
    for index, (decision, incoming) in enumerate(
        (("accepted", accepted), ("exact_replay", accepted), ("conflict", conflicting)),
        start=1,
    ):
        entry = build_outcome_reconciliation_entry(
            reconciliation_id=f"{index:08d}-0000-4000-8000-{index:012d}",
            decision=decision,
            incoming=incoming,
            durable=accepted,
            sequence_no=index,
            previous_entry_hash=previous,
            recorded_at=now + timedelta(seconds=index),
            **identifiers,
        )
        entries.append(_entry_dict(entry))
        previous = entry.entry_hash
    return {
        "schema_version": 1,
        "kind": "continuum.outcome-replay-cas.report",
        "source_head": "1" * 40,
        "deployment_artifact_sha256": "2" * 64,
        "workflow": {"run_id": 123, "run_attempt": 1},
        "migration": {"applied": [32, 33], "adopted": [], "current_version": 33},
        "database": {
            "engine": "CockroachDB",
            "scope_sql_role": "continuum_scope_1234567890abcdef",
            "rls": {
                "all_visible_reconciliations_in_scope": True,
                "proposal_visible_rows": 3,
            },
        },
        "provider": {
            "adapter": "aws-s3",
            "capability_manifest": {
                "supports_idempotency": True,
                "receipt_lookup": True,
                "reconciliation_timeout_seconds": 0,
            },
            "accepted_object_sha256": "3" * 64,
            "conflicting_object_sha256": "4" * 64,
            "accepted_receipt_sha256": hashlib.sha256(
                ("aws-s3:" + "a" * 64).encode()
            ).hexdigest(),
            "conflicting_receipt_sha256": hashlib.sha256(
                ("aws-s3:" + "c" * 64).encode()
            ).hexdigest(),
        },
        "cas": {
            "outcome_rows": 1,
            "canonical_promotions": 1,
            "journal_rows": 3,
            "first_replayed": False,
            "exact_replayed": True,
            "conflict_error_code": "OUTCOME_REPLAY_CONFLICT",
            "journal": entries,
            "chain_tip": entries[-1]["entry_hash"],
        },
        "gate": {
            "one_durable_outcome": True,
            "one_canonical_promotion": True,
            "exact_replay_idempotent": True,
            "conflicting_replay_rejected": True,
            "conflict_committed_before_error": True,
            "journal_hash_chain_valid": True,
            "scope_rls_valid": True,
            "status": "PASS",
        },
    }


class OutcomeReplayProofTests(unittest.TestCase):
    def test_public_projection_preserves_recomputable_chain(self):
        report = valid_report()
        validate_outcome_replay_proof(report)

        public = build_public_outcome_replay_proof(report)

        self.assertEqual(public["kind"], PUBLIC_KIND)
        self.assertEqual(public["cas"]["chain_tip"], report["cas"]["chain_tip"])
        validate_outcome_replay_proof(public)

    def test_journal_identity_tampering_fails_closed(self):
        report = valid_report()
        report["cas"]["journal"][2]["durable"]["provider_receipt_id"] = (
            "aws-s3:" + "f" * 64
        )

        with self.assertRaisesRegex(ValueError, "identity|hash"):
            validate_outcome_replay_proof(report)

    def test_uncommitted_conflict_claim_fails_closed(self):
        report = deepcopy(valid_report())
        report["gate"]["conflict_committed_before_error"] = False

        with self.assertRaisesRegex(ValueError, "gate"):
            validate_outcome_replay_proof(report)

    def test_readonly_judge_binds_exact_workflow_artifact_and_chain(self):
        raw = valid_report()
        public = build_public_outcome_replay_proof(raw)
        private_bytes = (json.dumps(raw, sort_keys=True) + "\n").encode()
        public_bytes = (
            json.dumps(public, indent=2, sort_keys=True) + "\n"
        ).encode()
        reference = build_reference(
            raw,
            public,
            private_bytes=private_bytes,
            public_bytes=public_bytes,
            repository="owner/repo",
            artifact_id=456,
            artifact_name=(
                "continuum-outcome-replay-cas-" + raw["source_head"] + "-123-1"
            ),
            artifact_archive_sha256="a" * 64,
            page_url="https://example.test/outcome-replay-cas.html",
            public_url="https://example.test/outcome-replay-cas-v1.json",
        )
        evidence = {
            "source": {"repository": "owner/repo"},
            "outcome_replay_cas": reference,
        }

        def fetch_json(url):
            if url == reference["workflow_api_url"]:
                return {
                    "id": 123,
                    "run_attempt": 1,
                    "head_sha": raw["source_head"],
                    "conclusion": "success",
                }
            if url == reference["artifact_api_url"]:
                return {
                    "id": 456,
                    "name": reference["artifact_name"],
                    "digest": "sha256:" + "a" * 64,
                    "expired": False,
                    "workflow_run": {"id": 123},
                }
            raise AssertionError(url)

        self.assertTrue(
            verify_outcome_replay_cas(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=lambda url: public_bytes,
            )
        )

        tampered = json.loads(public_bytes)
        tampered["cas"]["outcome_rows"] = 2
        self.assertFalse(
            verify_outcome_replay_cas(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=lambda url: json.dumps(tampered).encode(),
            )
        )


if __name__ == "__main__":
    unittest.main()

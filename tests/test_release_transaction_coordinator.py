import copy
import unittest

from scripts.release_transaction_coordinator import (
    advance_receipt,
    initialize_receipt,
    reconcile_receipt,
    verify_receipt,
)


class ReleaseTransactionCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = "owner/repository"
        self.tag = "hackathon-v10"
        self.source = "a" * 40
        self.envelope = "b" * 64
        self.assets = {
            "continuum-release-envelope-v2.json": self.envelope,
            "agent-ablation-v3.json": "c" * 64,
        }
        self.prepared = initialize_receipt(
            repository=self.repository,
            release_tag=self.tag,
            source_digest=self.source,
            envelope_sha256=self.envelope,
            evidence={
                "release_id": 42,
                "release_draft": True,
                "release_target": self.source,
                "envelope_sha256": self.envelope,
                "expected_asset_digests": self.assets,
            },
            observed_at="2026-08-08T00:00:00Z",
        )

    def _author(self, receipt=None):
        return advance_receipt(
            receipt or self.prepared,
            to_state="AUTHOR_ATTESTED",
            evidence={
                "author_attestation_count": 1,
                "author_bundle_sha256": "d" * 64,
                "signer_workflow": (
                    "owner/repository/.github/workflows/release-envelope.yml"
                ),
                "source_ref": "refs/heads/main",
                "rekor_log": "https://rekor.sigstore.dev",
            },
            observed_at="2026-08-08T00:01:00Z",
        )

    def _uploaded(self, receipt=None):
        expected = {**self.assets, "signature.jsonl": "d" * 64}
        return advance_receipt(
            receipt or self._author(),
            to_state="ASSETS_UPLOADED",
            evidence={
                "release_draft": True,
                "expected_asset_digests": expected,
                "observed_asset_digests": expected,
            },
            observed_at="2026-08-08T00:02:00Z",
        )

    def _immutable(self, receipt=None):
        return advance_receipt(
            receipt or self._uploaded(),
            to_state="IMMUTABLE",
            evidence={
                "immutable": True,
                "release_draft": False,
                "release_target": self.source,
                "release_tag": self.tag,
                "author_attestation_count": 1,
                "platform_attestation_count": 1,
                "total_attestation_count": 2,
            },
            observed_at="2026-08-08T00:03:00Z",
        )

    def _snapshot(self, **updates):
        snapshot = {
            "release_exists": True,
            "release_target": self.source,
            "envelope_sha256": self.envelope,
            "author_attestation_count": 0,
            "platform_attestation_count": 0,
            "immutable": False,
            "expected_asset_digests": self.assets,
            "observed_asset_digests": {},
            "pages": {},
        }
        snapshot.update(updates)
        return snapshot

    def test_happy_path_is_hash_chained_and_complete(self) -> None:
        immutable = self._immutable()
        complete = advance_receipt(
            immutable,
            to_state="PAGES_MATERIALIZED",
            evidence={
                "status": "success",
                "pages_workflow_run_id": 99,
                "pages_workflow_url": "https://github.com/owner/repository/actions/runs/99",
                "pages_source_digest": self.source,
                "coordinator_workflow_run_id": 98,
                "coordinator_workflow_url": "https://github.com/owner/repository/actions/runs/98",
                "coordinator_source_digest": "f" * 40,
                "coordinator_artifact_id": 97,
                "coordinator_artifact_name": (
                    "release-transaction-hackathon-v10-" + "f" * 40
                ),
                "coordinator_artifact_digest": "sha256:" + "9" * 64,
                "coordinator_receipt_sha256": "8" * 64,
                "public_receipt_url": "https://example.test/receipt.json",
                "release_tag": self.tag,
                "release_target": self.source,
                "public_bundle_sha256": "e" * 64,
            },
            observed_at="2026-08-08T00:04:00Z",
        )
        verify_receipt(complete)
        self.assertEqual(complete["state"], "PAGES_MATERIALIZED")
        self.assertEqual(complete["revision"], 4)
        self.assertEqual(len(complete["events"]), 5)
        self.assertEqual(
            reconcile_receipt(complete, self._snapshot())["next_action"],
            "COMPLETE",
        )

    def test_tampered_evidence_breaks_hash_chain(self) -> None:
        tampered = copy.deepcopy(self._author())
        tampered["events"][0]["evidence"]["release_id"] = 7
        with self.assertRaisesRegex(RuntimeError, "evidence digest mismatch"):
            verify_receipt(tampered)

    def test_transition_cannot_skip(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "transitions cannot skip"):
            advance_receipt(
                self.prepared,
                to_state="IMMUTABLE",
                evidence={},
                observed_at="2026-08-08T00:01:00Z",
            )

    def test_sensitive_evidence_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "sensitive evidence key"):
            initialize_receipt(
                repository=self.repository,
                release_tag=self.tag,
                source_digest=self.source,
                envelope_sha256=self.envelope,
                evidence={"api_token": "must-not-be-recorded"},
                observed_at="2026-08-08T00:00:00Z",
            )

    def test_crash_after_prepare_signs_once(self) -> None:
        plan = reconcile_receipt(self.prepared, self._snapshot())
        self.assertEqual(plan["next_action"], "SIGN_AUTHOR")

    def test_crash_after_provider_sign_before_ack_records_existing_signature(self) -> None:
        plan = reconcile_receipt(
            self.prepared,
            self._snapshot(author_attestation_count=1),
        )
        self.assertEqual(plan["next_action"], "RECORD_AUTHOR_ATTESTED")

    def test_crash_during_asset_upload_resumes_missing_assets(self) -> None:
        plan = reconcile_receipt(
            self._author(),
            self._snapshot(
                author_attestation_count=1,
                observed_asset_digests={
                    "continuum-release-envelope-v2.json": self.envelope
                },
            ),
        )
        self.assertEqual(plan["next_action"], "UPLOAD_MISSING_ASSETS")

    def test_crash_after_asset_upload_records_provider_state(self) -> None:
        plan = reconcile_receipt(
            self._author(),
            self._snapshot(
                author_attestation_count=1,
                observed_asset_digests=self.assets,
            ),
        )
        self.assertEqual(plan["next_action"], "RECORD_ASSETS_UPLOADED")

    def test_crash_before_publish_resumes_publication(self) -> None:
        plan = reconcile_receipt(
            self._uploaded(),
            self._snapshot(author_attestation_count=1),
        )
        self.assertEqual(plan["next_action"], "PUBLISH_IMMUTABLE")

    def test_crash_after_publish_before_ack_records_immutable(self) -> None:
        plan = reconcile_receipt(
            self._uploaded(),
            self._snapshot(
                author_attestation_count=1,
                platform_attestation_count=1,
                immutable=True,
            ),
        )
        self.assertEqual(plan["next_action"], "RECORD_IMMUTABLE")

    def test_crash_before_pages_dispatch_is_reconciled(self) -> None:
        plan = reconcile_receipt(
            self._immutable(),
            self._snapshot(
                author_attestation_count=1,
                platform_attestation_count=1,
                immutable=True,
            ),
        )
        self.assertEqual(plan["next_action"], "DISPATCH_PAGES")

    def test_successful_pages_receipt_is_recorded(self) -> None:
        plan = reconcile_receipt(
            self._immutable(),
            self._snapshot(
                author_attestation_count=1,
                platform_attestation_count=1,
                immutable=True,
                pages={
                    "status": "success",
                    "release_tag": self.tag,
                    "release_target": self.source,
                },
            ),
        )
        self.assertEqual(plan["next_action"], "RECORD_PAGES_MATERIALIZED")

    def test_conflicting_target_is_ambiguous(self) -> None:
        plan = reconcile_receipt(
            self.prepared, self._snapshot(release_target="f" * 40)
        )
        self.assertEqual(plan["status"], "AMBIGUOUS")

    def test_duplicate_author_attestation_is_ambiguous(self) -> None:
        plan = reconcile_receipt(
            self.prepared, self._snapshot(author_attestation_count=2)
        )
        self.assertEqual(plan["status"], "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()

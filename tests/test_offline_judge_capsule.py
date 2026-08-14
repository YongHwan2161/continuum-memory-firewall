import hashlib
import json
import unittest
from copy import deepcopy

from scripts.offline_judge_capsule import (
    CAPSULE_ASSET_NAME,
    UI_CHECK_SOURCES,
    build_capsule,
    capsule_receipt_sha256,
    relay_capsule,
    verify_capsule,
    verify_envelope_binding,
)
from scripts.release_transaction_coordinator import (
    advance_receipt,
    initialize_receipt,
)


class OfflineJudgeCapsuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.predecessor_target = "a" * 40
        self.successor_target = "b" * 40
        self.envelope_sha = "c" * 64
        self.author_bytes = b'{"author":true}\n'
        self.network_bytes = b'{"author":true}\n{"platform":true}\n'
        self.evidence = {
            "schema_version": 15,
            "release_envelope": {
                "tag": "hackathon-v22",
                "asset_name": "continuum-release-envelope-v2.json",
            },
            "network_sign_once": {
                "author_bundle_asset_name": (
                    "continuum-release-envelope-v2.sigstore.jsonl"
                )
            },
        }
        self.evidence_bytes = (
            json.dumps(self.evidence, indent=2, sort_keys=True) + "\n"
        ).encode()
        self.report_checks = {
            source: True
            for sources in UI_CHECK_SOURCES.values()
            for source in sources
        }
        self.report_checks["submission_recorded"] = True
        self.report = {
            "ok": True,
            "mode": "read-only-http-get",
            "checks": self.report_checks,
            "workflow_run_id": 10,
            "vector_benchmark_run_id": 11,
            "agent_pressure_run_id": 12,
            "agent_ablation_run_id": 13,
            "deployment_head_sha": "d" * 40,
        }
        author_sha = hashlib.sha256(self.author_bytes).hexdigest()
        network_sha = hashlib.sha256(self.network_bytes).hexdigest()
        self.asset_digests = {
            "continuum-release-envelope-v2.json": self.envelope_sha
        }
        self.release = {
            "immutable": True,
            "draft": False,
            "tag_name": "hackathon-v22",
            "target_commitish": self.predecessor_target,
            "assets": [
                {
                    "name": "continuum-release-envelope-v2.json",
                    "digest": "sha256:" + self.envelope_sha,
                },
                {
                    "name": "continuum-release-envelope-v2.sigstore.jsonl",
                    "digest": "sha256:" + author_sha,
                },
            ],
        }
        receipt = initialize_receipt(
            repository="o/r",
            release_tag="hackathon-v22",
            source_digest=self.predecessor_target,
            envelope_sha256=self.envelope_sha,
            evidence={
                "release_id": 1,
                "release_draft": True,
                "release_target": self.predecessor_target,
                "envelope_sha256": self.envelope_sha,
                "expected_asset_digests": self.asset_digests,
            },
            observed_at="2026-08-12T00:00:00Z",
        )
        receipt = advance_receipt(
            receipt,
            to_state="AUTHOR_ATTESTED",
            evidence={
                "author_attestation_count": 1,
                "author_bundle_sha256": author_sha,
                "signer_workflow": "o/r/.github/workflows/release-envelope.yml",
                "source_ref": "refs/heads/main",
                "rekor_log": "https://rekor.sigstore.dev",
            },
            observed_at="2026-08-12T00:01:00Z",
        )
        receipt = advance_receipt(
            receipt,
            to_state="ASSETS_UPLOADED",
            evidence={
                "release_draft": True,
                "expected_asset_digests": self.asset_digests,
                "observed_asset_digests": self.asset_digests,
            },
            observed_at="2026-08-12T00:02:00Z",
        )
        receipt = advance_receipt(
            receipt,
            to_state="IMMUTABLE",
            evidence={
                "immutable": True,
                "release_draft": False,
                "release_target": self.predecessor_target,
                "release_tag": "hackathon-v22",
                "author_attestation_count": 1,
                "platform_attestation_count": 1,
                "total_attestation_count": 2,
            },
            observed_at="2026-08-12T00:03:00Z",
        )
        self.immutable_receipt = deepcopy(receipt)
        self.receipt = advance_receipt(
            receipt,
            to_state="PAGES_MATERIALIZED",
            evidence={
                "status": "success",
                "pages_workflow_run_id": 31,
                "pages_workflow_url": "https://github.com/o/r/actions/runs/31",
                "pages_source_digest": self.predecessor_target,
                "coordinator_workflow_run_id": 30,
                "coordinator_workflow_url": (
                    "https://github.com/o/r/actions/runs/30"
                ),
                "coordinator_source_digest": self.predecessor_target,
                "coordinator_artifact_id": 29,
                "coordinator_artifact_name": (
                    "release-transaction-hackathon-v22-"
                    + self.predecessor_target
                ),
                "coordinator_artifact_digest": "sha256:" + "e" * 64,
                "coordinator_receipt_sha256": "f" * 64,
                "public_receipt_url": (
                    "https://example.test/release-transaction-receipt.json"
                ),
                "release_tag": "hackathon-v22",
                "release_target": self.predecessor_target,
                "public_bundle_sha256": network_sha,
            },
            observed_at="2026-08-12T00:04:00Z",
        )
        self.transaction_bytes = (
            json.dumps(self.receipt, indent=2, sort_keys=True) + "\n"
        ).encode()

    def build(self):
        return build_capsule(
            evidence_url="https://example.test/evidence/judge-verification.json",
            evidence_bytes=self.evidence_bytes,
            verification_report=self.report,
            predecessor_release=self.release,
            transaction_receipt=self.receipt,
            transaction_bytes=self.transaction_bytes,
            author_bundle_bytes=self.author_bytes,
            network_bundle_bytes=self.network_bytes,
            compiler_repository="o/r",
            compiler_source_head=self.successor_target,
            compiler_workflow_run_id=20,
            compiler_workflow_attempt=1,
            compiler_release_tag="hackathon-v23",
            observed_at="2026-08-12T01:00:00Z",
        )

    def test_builds_self_hashed_zero_api_capsule(self) -> None:
        capsule = self.build()
        result = verify_capsule(capsule)
        self.assertTrue(result["ok"])
        self.assertEqual(result["github_api_requests_per_judge_click"], 0)
        self.assertEqual(result["online_check_count"], len(self.report_checks))
        self.assertEqual(result["ui_check_count"], len(UI_CHECK_SOURCES))
        self.assertEqual(capsule["receipt_sha256"], capsule_receipt_sha256(capsule))
        self.assertEqual(capsule["predecessor"]["release_tag"], "hackathon-v22")

    def test_release_envelope_binds_exact_capsule_bytes(self) -> None:
        capsule = self.build()
        capsule_bytes = (json.dumps(capsule, indent=2, sort_keys=True) + "\n").encode()
        capsule_sha = hashlib.sha256(capsule_bytes).hexdigest()
        envelope = {
            "release": {
                "commit_sha": self.successor_target,
                "tag": "hackathon-v23",
            },
            "offline_judge_capsule": {
                "schema_version": 1,
                "asset_name": CAPSULE_ASSET_NAME,
                "asset_sha256": capsule_sha,
                "receipt_sha256": capsule["receipt_sha256"],
            },
        }
        result = verify_envelope_binding(
            capsule=capsule,
            capsule_bytes=capsule_bytes,
            envelope=envelope,
        )
        self.assertEqual(result["asset_sha256"], capsule_sha)

        envelope["offline_judge_capsule"]["asset_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "file digest"):
            verify_envelope_binding(
                capsule=capsule,
                capsule_bytes=capsule_bytes,
                envelope=envelope,
            )

    def test_recomputed_receipt_cannot_hide_failed_online_check(self) -> None:
        capsule = self.build()
        capsule["online_verification"]["checks"]["workflow_succeeded"] = False
        capsule["receipt_sha256"] = capsule_receipt_sha256(capsule)
        with self.assertRaisesRegex(RuntimeError, "failed online check"):
            verify_capsule(capsule)

    def test_ui_source_mapping_is_fail_closed(self) -> None:
        capsule = self.build()
        capsule["ui_check_sources"]["workflow"] = ["submission_recorded"]
        capsule["receipt_sha256"] = capsule_receipt_sha256(capsule)
        with self.assertRaisesRegex(RuntimeError, "source mapping"):
            verify_capsule(capsule)

    def test_relays_last_successful_capsule_without_promoting_failed_epoch(
        self,
    ) -> None:
        capsule = self.build()
        capsule_bytes = (
            json.dumps(capsule, indent=2, sort_keys=True) + "\n"
        ).encode()
        asset_sha = hashlib.sha256(capsule_bytes).hexdigest()

        relayed = relay_capsule(
            capsule,
            capsule_bytes=capsule_bytes,
            expected_asset_sha256=asset_sha,
            expected_receipt_sha256=capsule["receipt_sha256"],
            source_release_tag="hackathon-v23",
            source_release_target=self.successor_target,
            compiler_repository="o/r",
            compiler_source_head="f" * 40,
            compiler_workflow_run_id=99,
            compiler_workflow_attempt=1,
            compiler_release_tag="hackathon-v24",
            failed_pages_workflow_run_id=101,
            observed_at="2026-08-12T02:00:00Z",
        )

        self.assertTrue(verify_capsule(relayed)["ok"])
        self.assertEqual(relayed["predecessor"], capsule["predecessor"])
        self.assertEqual(relayed["relay"]["source_asset_sha256"], asset_sha)
        self.assertEqual(
            relayed["relay"]["source_receipt_sha256"],
            capsule["receipt_sha256"],
        )
        self.assertEqual(
            relayed["relay"]["source_compiler_workflow_run_id"], 20
        )
        self.assertEqual(
            relayed["relay"]["failed_pages_workflow_run_id"], 101
        )
        self.assertIs(
            relayed["relay"]["failed_epoch_promoted_to_pass"], False
        )
        self.assertEqual(
            relayed["compiler"]["successor_release_tag"], "hackathon-v24"
        )
        self.assertNotEqual(
            relayed["receipt_sha256"], capsule["receipt_sha256"]
        )
        relayed_bytes = (
            json.dumps(relayed, indent=2, sort_keys=True) + "\n"
        ).encode()
        envelope = {
            "release": {
                "commit_sha": "f" * 40,
                "tag": "hackathon-v24",
            },
            "offline_judge_capsule": {
                "schema_version": 1,
                "asset_name": CAPSULE_ASSET_NAME,
                "asset_sha256": hashlib.sha256(relayed_bytes).hexdigest(),
                "receipt_sha256": relayed["receipt_sha256"],
                "relay": deepcopy(relayed["relay"]),
            },
        }
        self.assertTrue(
            verify_envelope_binding(
                capsule=relayed,
                capsule_bytes=relayed_bytes,
                envelope=envelope,
            )["ok"]
        )
        envelope["offline_judge_capsule"]["relay"][
            "failed_epoch_promoted_to_pass"
        ] = True
        with self.assertRaisesRegex(RuntimeError, "relay mismatch"):
            verify_envelope_binding(
                capsule=relayed,
                capsule_bytes=relayed_bytes,
                envelope=envelope,
            )

        with self.assertRaisesRegex(
            RuntimeError, "relay source capsule identity mismatch"
        ):
            relay_capsule(
                capsule,
                capsule_bytes=capsule_bytes,
                expected_asset_sha256="0" * 64,
                expected_receipt_sha256=capsule["receipt_sha256"],
                source_release_tag="hackathon-v23",
                source_release_target=self.successor_target,
                compiler_repository="o/r",
                compiler_source_head="f" * 40,
                compiler_workflow_run_id=99,
                compiler_workflow_attempt=1,
                compiler_release_tag="hackathon-v24",
                failed_pages_workflow_run_id=101,
            )

    def test_terminal_network_mismatch_blocks_compilation(self) -> None:
        bad_receipt = advance_receipt(
            self.immutable_receipt,
            to_state="PAGES_MATERIALIZED",
            evidence={
                "status": "success",
                "pages_workflow_run_id": 31,
                "pages_workflow_url": "https://github.com/o/r/actions/runs/31",
                "pages_source_digest": self.predecessor_target,
                "coordinator_workflow_run_id": 30,
                "coordinator_workflow_url": (
                    "https://github.com/o/r/actions/runs/30"
                ),
                "coordinator_source_digest": self.predecessor_target,
                "coordinator_artifact_id": 29,
                "coordinator_artifact_name": (
                    "release-transaction-hackathon-v22-"
                    + self.predecessor_target
                ),
                "coordinator_artifact_digest": "sha256:" + "e" * 64,
                "coordinator_receipt_sha256": "f" * 64,
                "public_receipt_url": (
                    "https://example.test/release-transaction-receipt.json"
                ),
                "release_tag": "hackathon-v22",
                "release_target": self.predecessor_target,
                "public_bundle_sha256": "0" * 64,
            },
            observed_at="2026-08-12T00:04:00Z",
        )
        with self.assertRaisesRegex(RuntimeError, "network bundle"):
            build_capsule(
                evidence_url="https://example.test/evidence/judge.json",
                evidence_bytes=self.evidence_bytes,
                verification_report=self.report,
                predecessor_release=self.release,
                transaction_receipt=bad_receipt,
                transaction_bytes=self.transaction_bytes,
                author_bundle_bytes=self.author_bytes,
                network_bundle_bytes=self.network_bytes,
                compiler_repository="o/r",
                compiler_source_head=self.successor_target,
                compiler_workflow_run_id=20,
                compiler_workflow_attempt=1,
                compiler_release_tag="hackathon-v23",
            )


if __name__ == "__main__":
    unittest.main()

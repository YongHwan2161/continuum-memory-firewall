from __future__ import annotations

from pathlib import Path
import unittest

from continuum.kms_authority_proof import (
    seal_kms_authority_proof,
    validate_kms_authority_proof,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aws-kms-outcome-authority-proof.yml"


def valid_report():
    return seal_kms_authority_proof(
        {
            "attestation": {
                "canonical_promotions": 3,
                "consumed_rows": 3,
                "distinct_public_keys": 2,
                "exact_replay_rows": 1,
                "issuer": "s3-provider-origin-verifier-kms-v2",
                "persisted_algorithm": "ECDSA_SHA_256",
                "persisted_authority_epochs": [1, 2, 3],
                "persisted_key_arn_digests": 3,
                "policy_version": "s3-receipt-lookup-kms-v2",
                "raw_handle_persisted": False,
                "ttl_seconds": 300,
            },
            "aws": {
                "action_worker_arn_sha256": "a" * 64,
                "action_worker_kms_error_code": "AccessDenied",
                "action_worker_kms_sign_denied": True,
                "key_spec": "ECC_NIST_P256",
                "kms_get_public_key_calls": 2,
                "kms_sign_calls": 4,
                "region": "ap-southeast-1",
                "s3_head_get_lookups": 4,
                "signing_algorithm": "ECDSA_SHA_256",
                "verifier_key_count": 2,
                "verifier_role_arn_sha256": "b" * 64,
            },
            "cockroachdb": {
                "attestation_rows": 3,
                "canonical_memory_rows": 3,
                "migration_version": 38,
                "outcome_rows": 3,
                "rls_scope_visible_rows": 3,
                "runtime_attestation_insert_sqlstate": "42501",
            },
            "gate": {
                "checks": {f"check_{index:02d}": True for index in range(18)},
                "status": "PASS",
            },
            "kind": "continuum.kms-outcome-authority-lifecycle",
            "lifecycle": {
                "authority_epochs": [1, 2, 3],
                "dual_key_overlap_verified": True,
                "keyring_versions": [1, 2, 3],
                "manifest_sha256": ["c" * 64, "d" * 64, "e" * 64],
                "old_handle_replayed_without_resigning": True,
                "private_handoff_objects_remaining": 0,
                "restart_verified_offline": True,
                "rollback_verified": True,
                "transitions": [
                    "ACTIVATE_KEY_A",
                    "ROTATE_TO_KEY_B",
                    "ROLLBACK_TO_KEY_A",
                ],
            },
            "negative_paths": {
                "expired": "OUTCOME_ATTESTATION_EXPIRED",
                "forged": "OUTCOME_ATTESTATION_INVALID",
                "unknown_key_epoch": "OUTCOME_ATTESTATION_INVALID",
                "worker_kms_sign": "AccessDenied",
            },
            "schema_version": 1,
            "source": {
                "deployment_artifact_sha256": "f" * 64,
                "head": "1" * 40,
                "workflow_run_attempt": 1,
                "workflow_run_id": 123,
            },
        }
    )


class KmsAuthorityProofTests(unittest.TestCase):
    def test_public_receipt_is_self_hashed_and_private_authority_free(self):
        report = valid_report()
        validate_kms_authority_proof(report)
        self.assertEqual(len(report["receipt_sha256"]), 64)
        self.assertNotIn("arn:aws", repr(report))
        self.assertNotIn("v2.", repr(report))

    def test_tamper_and_raw_handle_are_rejected(self):
        report = valid_report()
        report["aws"]["kms_sign_calls"] = 5
        with self.assertRaises(ValueError):
            validate_kms_authority_proof(report)

        report = valid_report()
        report["attestation"]["handle"] = "v2.private.signature"
        with self.assertRaises(ValueError):
            seal_kms_authority_proof(report)

    def test_workflow_separates_verifier_and_worker_then_scrubs_handoff(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("environment: continuum-production", text)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', text)
        self.assertIn("CONTINUUM_KMS_VERIFIER_ROLE_ARN", text)
        self.assertIn("continuum-provider-verifier", text)
        self.assertIn("action worker unexpectedly called kms:Sign", (
            ROOT / "scripts" / "run_kms_authority_lifecycle_proof.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("ContinuumKmsAuthorityOneCommand", text)
        self.assertIn("aws iam delete-role-policy", text)
        self.assertIn("private-request-v1.json", text)
        self.assertIn("private-issuance-v1.json", text)
        self.assertIn("--recursive", text)
        self.assertIn("if: always()", text)
        self.assertNotIn("AWS_ACCESS_KEY_ID", text)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", text)


if __name__ == "__main__":
    unittest.main()

import unittest

from continuum.adaptive_diagnosis import ADAPTIVE_DIAGNOSIS_FAMILIES
from continuum.transfer_firewall import causal_signature
from scripts.transfer_firewall_fixture import (
    ATTESTATION_OPERATION,
    run_transfer_fixture,
)


class TransferFirewallFixtureTests(unittest.TestCase):
    def test_attestation_is_read_only_and_profile_changes_workspace(self) -> None:
        signatures = []
        workspace_digests = []
        for index, profile in enumerate(("source-monorepo", "target-service")):
            receipt, _ = run_transfer_fixture(
                case_id=f"tf-{index:020x}",
                fixture_id="python-runtime",
                environment_profile_id=profile,
                environment_fingerprint=f"env-{index:020x}",
                operation_kind="target-attestation",
                operation_id=ATTESTATION_OPERATION,
                commitment_sha256="b" * 64,
            )
            payload = receipt["provider_payload"]
            self.assertTrue(receipt["exercise_passed"])
            self.assertTrue(payload["read_only"])
            self.assertEqual(
                payload["workspace_sha256_before"],
                payload["workspace_sha256_after"],
            )
            self.assertEqual(
                payload["causal_signature"], causal_signature("python-runtime")
            )
            signatures.append(payload["causal_signature"])
            workspace_digests.append(payload["workspace_sha256_before"])
        self.assertEqual(len(set(signatures)), 1)
        self.assertEqual(len(set(workspace_digests)), 2)

    def test_only_target_family_patch_recovers_in_changed_environment(self) -> None:
        for index, family in enumerate(ADAPTIVE_DIAGNOSIS_FAMILIES):
            common = {
                "case_id": f"tf-{index:020x}",
                "fixture_id": family.family,
                "environment_profile_id": "target-container",
                "environment_fingerprint": f"env-{index:020x}",
                "operation_kind": "remediation",
                "commitment_sha256": "b" * 64,
            }
            wrong, _ = run_transfer_fixture(
                **common, operation_id=family.wrong_patch_id
            )
            green, _ = run_transfer_fixture(
                **common, operation_id=family.expected_patch_id
            )
            self.assertFalse(wrong["exercise_passed"])
            self.assertTrue(green["exercise_passed"])
            self.assertFalse(green["repository_mutation"])
            self.assertEqual(green["cleanup_residual_count"], 0)

    def test_source_green_receipt_attests_the_causal_signature(self) -> None:
        receipt, _ = run_transfer_fixture(
            case_id="tf-00000000000000000001",
            fixture_id="python-runtime",
            environment_profile_id="source-monorepo",
            environment_fingerprint="env-00000000000000000001",
            operation_kind="source-calibration",
            operation_id="set_python_312",
            commitment_sha256="b" * 64,
        )
        self.assertTrue(receipt["exercise_passed"])
        self.assertEqual(
            receipt["provider_payload"]["causal_signature"],
            causal_signature("python-runtime"),
        )


if __name__ == "__main__":
    unittest.main()

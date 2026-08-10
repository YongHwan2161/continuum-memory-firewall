import unittest

from continuum.adaptive_diagnosis import ADAPTIVE_DIAGNOSIS_FAMILIES
from scripts.adaptive_diagnosis_fixture import run_adaptive_fixture


class AdaptiveDiagnosisFixtureTests(unittest.TestCase):
    def test_each_pair_is_read_only_and_only_the_reviewed_patch_is_green(self) -> None:
        for index, family in enumerate(ADAPTIVE_DIAGNOSIS_FAMILIES):
            case_id = f"ad-{index:020x}"
            for probe_id in (family.fault_probe_id, family.paired_probe_id):
                with self.subTest(family=family.family, probe=probe_id):
                    receipt, _ = run_adaptive_fixture(
                        case_id=case_id,
                        fixture_id=family.family,
                        operation_kind="diagnostic",
                        operation_id=probe_id,
                        commitment_sha256="b" * 64,
                    )
                    self.assertTrue(receipt["exercise_passed"])
                    payload = receipt["provider_payload"]
                    self.assertTrue(payload["read_only"])
                    self.assertEqual(
                        payload["workspace_sha256_before"],
                        payload["workspace_sha256_after"],
                    )
                    self.assertEqual(receipt["cleanup_residual_count"], 0)
            with self.subTest(family=family.family, remediation="wrong"):
                wrong, _ = run_adaptive_fixture(
                    case_id=case_id,
                    fixture_id=family.family,
                    operation_kind="remediation",
                    operation_id=family.wrong_patch_id,
                    commitment_sha256="b" * 64,
                )
                self.assertFalse(wrong["exercise_passed"])
            with self.subTest(family=family.family, remediation="green"):
                green, _ = run_adaptive_fixture(
                    case_id=case_id,
                    fixture_id=family.family,
                    operation_kind="remediation",
                    operation_id=family.expected_patch_id,
                    commitment_sha256="b" * 64,
                )
                self.assertTrue(green["exercise_passed"])
                self.assertFalse(green["repository_mutation"])
                self.assertEqual(green["cleanup_residual_count"], 0)


if __name__ == "__main__":
    unittest.main()

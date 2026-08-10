import unittest

from continuum.adaptive_diagnosis import evidence_patch_id


class AdaptiveDiagnosisEvidenceRoutingTests(unittest.TestCase):
    def test_anomaly_routes_each_probe_to_its_reviewed_patch(self) -> None:
        expected = {
            "inspect_runtime_manifest": "set_python_312",
            "inspect_package_settings": "normalize_package_root",
            "inspect_dependency_lock": "restore_dependency_lock",
            "inspect_matrix_manifest": "repair_matrix_axis",
            "inspect_artifact_tree": "restore_artifact_path",
            "inspect_report_schema": "repair_gate_schema",
        }
        self.assertEqual(
            {probe: evidence_patch_id(probe, "anomaly") for probe in expected},
            expected,
        )

    def test_within_contract_routes_to_the_mutually_exclusive_pair(self) -> None:
        expected = {
            "inspect_runtime_manifest": "normalize_package_root",
            "inspect_package_settings": "set_python_312",
            "inspect_dependency_lock": "repair_matrix_axis",
            "inspect_matrix_manifest": "restore_dependency_lock",
            "inspect_artifact_tree": "repair_gate_schema",
            "inspect_report_schema": "restore_artifact_path",
        }
        self.assertEqual(
            {
                probe: evidence_patch_id(probe, "within-contract")
                for probe in expected
            },
            expected,
        )

    def test_unknown_or_untrusted_facts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "not registered"):
            evidence_patch_id("inspect_everything", "anomaly")
        with self.assertRaisesRegex(ValueError, "finding is invalid"):
            evidence_patch_id("inspect_runtime_manifest", "probably")


if __name__ == "__main__":
    unittest.main()

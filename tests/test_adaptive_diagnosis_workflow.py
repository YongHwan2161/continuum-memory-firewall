from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class AdaptiveDiagnosisWorkflowTests(unittest.TestCase):
    def test_parent_seals_before_candidate_and_uses_main_oidc(self) -> None:
        workflow = (
            ROOT / ".github/workflows/aws-adaptive-diagnosis-benchmark.yml"
        ).read_text(encoding="utf-8")
        generation = workflow.index("generate_adaptive_diagnosis.py")
        sealing = workflow.index("seal_adaptive_diagnosis.py")
        candidate = workflow.index("run_live_adaptive_diagnosis.py")
        self.assertLess(generation, sealing)
        self.assertLess(sealing, candidate)
        self.assertIn("environment: continuum-production", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', workflow)
        self.assertIn(".methodology.candidate_visible_label_fields == 0", workflow)
        self.assertIn(
            ".paired_comparisons.continuum_vs_stateless.recurrence.diagnostic_probe_exact_p_value <= 0.05",
            workflow,
        )
        self.assertIn("retention-days: 90", workflow)

    def test_child_is_read_only_to_repository_and_preserves_red_receipts(self) -> None:
        workflow = (
            ROOT / ".github/workflows/adaptive-diagnosis-child.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("scripts/adaptive_diagnosis_fixture.py", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("adaptive-diagnosis-${{ inputs.correlation_id }}", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertIn("commitment_sha256", workflow)

    def test_generic_provider_binds_extra_inputs_and_exact_receipt_filename(self) -> None:
        source = (ROOT / "scripts/run_live_ci_recovery.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("extra workflow inputs may not override reserved inputs", source)
        self.assertIn("self.receipt_filename", source)
        self.assertIn('receipt["provider_payload"]', source)


if __name__ == "__main__":
    unittest.main()

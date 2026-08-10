from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class CIRecoveryWorkflowTests(unittest.TestCase):
    def test_child_workflow_preserves_artifact_on_real_red_runs(self) -> None:
        workflow = (ROOT / ".github/workflows/ci-recovery-child.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run-name: ci-recovery / ${{ inputs.correlation_id }}", workflow)
        self.assertIn("scripts/ci_recovery_fixture.py", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("ci-recovery-${{ inputs.correlation_id }}", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertIn("contents: read", workflow)


    def test_parent_workflow_has_only_bounded_dispatch_and_main_oidc(self) -> None:
        workflow = (
            ROOT / ".github/workflows/aws-ci-recovery-benchmark.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("environment: continuum-production", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', workflow)
        self.assertIn("scripts/run_live_ci_recovery.py", workflow)
        self.assertIn(".methodology.total_child_workflow_runs == 54", workflow)
        self.assertIn(".arms.continuum.false_canonical_promotions == 0", workflow)
        self.assertIn("retention-days: 90", workflow)

    def test_artifact_redirect_never_forwards_the_github_bearer(self) -> None:
        controller = (ROOT / "scripts/run_live_ci_recovery.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Accept": "application/vnd.github+json"', controller)
        self.assertIn("class _NoRedirect", controller)
        self.assertIn("unsigned = Request(", controller)
        self.assertNotIn("application/octet-stream", controller)


if __name__ == "__main__":
    unittest.main()

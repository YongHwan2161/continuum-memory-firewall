from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BlindHoldoutWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = ROOT / ".github/workflows/aws-blind-holdout.yml"
        self.source = self.path.read_text(encoding="utf-8")
        self.sealer = (ROOT / "scripts/seal_blind_holdout.py").read_text(
            encoding="utf-8"
        )
    def test_workflow_is_main_environment_oidc_and_self_revoking(self) -> None:
        self.assertIn("permissions:\n  id-token: write\n  contents: write", self.source)
        self.assertIn("environment: continuum-production", self.source)
        self.assertIn("assert_deployer_identity.sh", self.source)
        self.assertIn("ContinuumBlindHoldoutOneRun", self.source)
        self.assertIn("delete-role-policy", self.source)
        self.assertIn("{revoked:true,run_id:$run_id}", self.source)
        cleanup = self.source.index("blind holdout bounded sandbox cleanup")
        revoke = self.source.rindex("delete-role-policy")
        self.assertLess(cleanup, revoke)
        self.assertIn("get-role-policy", self.source[revoke:])

    def test_generation_sealing_candidate_and_scorer_are_ordered(self) -> None:
        generation = self.source.index("generate_blind_holdout.py")
        sealing = self.source.index("seal_blind_holdout.py")
        candidate = self.source.index("run_live_blind_holdout.py")
        evaluator = self.source.index("score_blind_holdout.py")
        scoring_gate = self.source.index(".methodology.scored_after_both_arms == true")
        self.assertLess(generation, sealing)
        self.assertLess(sealing, candidate)
        self.assertLess(candidate, evaluator)
        self.assertLess(evaluator, scoring_gate)
        self.assertIn('IfNoneMatch="*"', self.sealer)
        self.assertIn("candidate_label_fields == 0", self.source)
        self.assertIn(
            '{Effect:"Deny",Action:"s3:GetObject",Resource:$labels}', self.source
        )
        candidate_step = self.source[
            self.source.index("Run label-free candidates against real disposable providers") :
            self.source.index("Open labels in a separate evaluator only after both arms finish")
        ]
        self.assertNotIn("labels_key", candidate_step)
        self.assertNotIn("--labels", candidate_step)

    def test_github_and_s3_effects_are_disposable_and_artifact_bound(self) -> None:
        self.assertIn('CONTINUUM_HOLDOUT_SANDBOX_PREFIX', self.source)
        self.assertIn("cleanup_blind_holdout.py", self.source)
        self.assertIn('name: continuum-blind-holdout-${{ github.sha }}', self.source)
        self.assertIn('.providers == ["github","s3"]', self.source)
        self.assertIn('retention-days: 90', self.source)


if __name__ == "__main__":
    unittest.main()

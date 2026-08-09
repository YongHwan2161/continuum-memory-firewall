from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SequentialBlindWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = ROOT / ".github/workflows/aws-sequential-blind-campaign.yml"
        self.source = self.path.read_text(encoding="utf-8")

    def test_main_environment_oidc_budget_and_node24_are_fixed(self) -> None:
        self.assertIn("runs-on: ubuntu-22.04", self.source)
        self.assertIn("environment: continuum-production", self.source)
        self.assertIn('[[ "$GITHUB_REF" == "refs/heads/main" ]]', self.source)
        self.assertIn("assert_deployer_identity.sh", self.source)
        self.assertIn("CONTINUUM_MONTHLY_BUDGET_USD=20", self.source)
        self.assertIn("# v7.0.1, Node 24", self.source)
        self.assertIn("# v6.2.3, Node 24", self.source)
        self.assertIn('python-version: "3.12"', self.source)

    def test_all_three_batches_and_manifest_are_sealed_before_candidates(self) -> None:
        generation = self.source.index("generate_sequential_blind_batch.py")
        batch_seal = self.source.index("seal_sequential_blind_batch.py")
        campaign_seal = self.source.index("seal_sequential_blind_campaign.py")
        candidate = self.source.index("run_live_sequential_blind.py")
        evaluator = self.source.index("score_sequential_blind.py")
        self.assertLess(generation, batch_seal)
        self.assertLess(batch_seal, campaign_seal)
        self.assertLess(campaign_seal, candidate)
        self.assertLess(candidate, evaluator)
        self.assertIn("for batch in 1 2 3", self.source)
        self.assertIn("commitment_sha256s", (ROOT / "scripts/seal_sequential_blind_campaign.py").read_text())

    def test_candidate_cannot_open_labels_or_scoring_manifest(self) -> None:
        policy = self.source.index("Replace preregistration access with label and manifest deny policy")
        candidate = self.source.index("Run three label-free batches with enforced start separation")
        evaluator = self.source.index("Open labels only after all 540 candidate observations finish")
        self.assertLess(policy, candidate)
        self.assertIn('{Effect:"Deny",Action:"s3:GetObject",Resource:$deny_get}', self.source)
        self.assertIn("CONTINUUM_SEQUENTIAL_DENIED_OBJECTS", self.source)
        candidate_source = self.source[candidate:evaluator]
        self.assertNotIn("labels.json", candidate_source)
        self.assertNotIn("campaign-manifest.json", candidate_source)
        self.assertIn("campaign-seal-receipt.json", candidate_source)

    def test_spacing_population_artifact_and_cleanup_are_hard_gates(self) -> None:
        self.assertIn("prior_epoch + 305", self.source)
        self.assertIn(".methodology.arm_observations == 540", self.source)
        self.assertIn("observed_start_separations_seconds[] >= 300", self.source)
        self.assertIn("ContinuumSequentialBlindOneRun", self.source)
        self.assertIn("CONTINUUM_SEQUENTIAL_SANDBOX_ACCESS_READY=1", self.source)
        self.assertIn(
            '${CONTINUUM_SEQUENTIAL_SANDBOX_ACCESS_READY:-0}', self.source
        )
        self.assertIn("delete-role-policy", self.source)
        self.assertIn("cleanup_blind_holdout.py", self.source)
        self.assertIn("{revoked:true,run_id:$run_id}", self.source)
        artifact = self.source.index("actions/upload-artifact")
        cleanup = self.source.index("Revoke temporary capabilities", artifact)
        self.assertLess(artifact, cleanup)
        self.assertIn("if: always()", self.source[artifact:cleanup])


class SequentialBlindEvaluatorReplayWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = (
            ROOT / ".github/workflows/sequential-blind-evaluator-replay.yml"
        )
        self.source = self.path.read_text(encoding="utf-8")

    def test_replay_is_main_only_python312_and_read_only(self) -> None:
        self.assertIn("actions: read", self.source)
        self.assertIn("contents: read", self.source)
        self.assertNotIn("id-token: write", self.source)
        self.assertIn('[[ "$GITHUB_REF" == refs/heads/main ]]', self.source)
        self.assertIn('python-version: "3.12"', self.source)
        self.assertIn("# v7.0.1, Node 24", self.source)
        self.assertIn("# v7.0.0, Node 24", self.source)

    def test_replay_binds_completed_candidate_cleanup_and_exact_artifact(self) -> None:
        for phrase in (
            "Run three label-free batches with enforced start separation",
            "Open labels only after all 540 candidate observations finish",
            "Revoke temporary capabilities, tombstone token, and prove sandbox cleanup",
            "candidate_artifact_archive_sha256",
            "artifact_receipt",
            "workflow_run.id",
        ):
            self.assertIn(phrase, self.source)
        download = self.source.index("Download only the exact preserved candidate artifact")
        score = self.source.index("Score once with reviewed Python")
        self.assertLess(download, score)
        self.assertIn("test ! -e \"$out/campaign-report.json\"", self.source)
        self.assertIn("--replay-reason github_runner_python_3_10_missing_strenum_before_scoring", self.source)
        self.assertIn("if: always()", self.source)


if __name__ == "__main__":
    unittest.main()

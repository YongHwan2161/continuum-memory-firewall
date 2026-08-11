from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class ReleaseGuardianWorkflowTests(unittest.TestCase):
    def test_batch_workflow_binds_time_replication_and_self_revokes(self) -> None:
        workflow = (ROOT / ".github/workflows/aws-release-guardian.yml").read_text(
            encoding="utf-8"
        )
        for replication_id in ("rg-101", "rg-203", "rg-307", "rg-409", "rg-503"):
            self.assertIn(replication_id, workflow)
        self.assertIn("--replication-set-id", workflow)
        self.assertIn("--replication-position", workflow)
        self.assertIn("--workflow-run-id '$GITHUB_RUN_ID'", workflow)
        self.assertIn(".schema_version == 2", workflow)
        self.assertIn("case_population_sha256", workflow)
        self.assertIn("${GITHUB_RUN_ID}-${CONTINUUM_REPLICATION_ID}.json", workflow)
        self.assertIn("aws iam delete-role-policy", workflow)
        self.assertIn("release-guardian-tombstone.json", workflow)

    def test_aggregate_workflow_is_read_only_and_requires_five_exact_artifacts(self) -> None:
        workflow = (
            ROOT / ".github/workflows/aggregate-release-guardian.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("actions: read", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertEqual(workflow.count("--report build/replications/rg-"), 5)
        self.assertIn("test \"$(jq -r .head_sha", workflow)
        self.assertIn("artifact_digest", workflow)
        self.assertIn("minimum_observed_start_separation_seconds >= 300", workflow)
        self.assertIn(".methodology.paired_cases == 180", workflow)
        self.assertIn(".methodology.arm_observations == 360", workflow)

    def test_every_aws_workflow_pins_the_reviewed_node24_credential_action(self) -> None:
        expected = (
            "aws-actions/configure-aws-credentials@"
            "e6de054238d6b7531b4efff3b6587d9aade6a06c # v6.2.3, Node 24"
        )
        workflows = list((ROOT / ".github/workflows").glob("aws-*.yml"))
        credential_workflows = [
            path
            for path in workflows
            if "configure-aws-credentials@" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(len(credential_workflows), 17)
        self.assertIn(
            "aws-ci-recovery-benchmark.yml",
            {path.name for path in credential_workflows},
        )
        self.assertIn(
            "aws-adaptive-diagnosis-benchmark.yml",
            {path.name for path in credential_workflows},
        )
        self.assertIn(
            "aws-transfer-firewall-benchmark.yml",
            {path.name for path in credential_workflows},
        )
        for path in credential_workflows:
            source = path.read_text(encoding="utf-8")
            self.assertIn(expected, source, path.name)
            self.assertNotIn("configure-aws-credentials@v4", source, path.name)


if __name__ == "__main__":
    unittest.main()

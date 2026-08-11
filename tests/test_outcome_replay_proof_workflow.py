from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aws-outcome-replay-cas-proof.yml"


class OutcomeReplayProofWorkflowTests(unittest.TestCase):
    def test_workflow_is_main_oidc_exact_prefix_and_self_revoking(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("environment: continuum-production", text)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', text)
        self.assertIn("id-token: write", text)
        self.assertIn("./scripts/assert_deployer_identity.sh", text)
        self.assertIn(
            "evidence/outcome-replay-cas/$GITHUB_SHA/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT",
            text,
        )
        self.assertIn("ContinuumOutcomeReplayCasOneCommand", text)
        self.assertIn("aws iam delete-role-policy", text)
        self.assertIn("if: always()", text)
        self.assertNotIn("AWS_ACCESS_KEY_ID", text)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", text)

    def test_public_judge_surface_binds_chain_and_immutable_asset(self):
        page = (ROOT / "public-demo" / "outcome-replay-cas.html").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "public-demo" / "verify.html").read_text(
            encoding="utf-8"
        )
        index = (ROOT / "public-demo" / "index.html").read_text(
            encoding="utf-8"
        )
        release = (ROOT / ".github" / "workflows" / "release-envelope.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("outcome-replay-cas-v1.json", page)
        self.assertIn("item.entry_hash===computed", page)
        self.assertIn("outcomeCasChain", verifier)
        self.assertIn("outcomeCasReleaseAsset", verifier)
        self.assertIn("./outcome-replay-cas.html", index)
        self.assertIn("outcome-replay-cas-v1.json.sha256", release)


if __name__ == "__main__":
    unittest.main()

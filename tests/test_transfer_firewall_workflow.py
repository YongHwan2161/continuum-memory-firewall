from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class TransferFirewallWorkflowTests(unittest.TestCase):
    def test_parent_seals_before_candidate_and_enforces_preregistered_gate(self) -> None:
        workflow = (
            ROOT / ".github/workflows/aws-transfer-firewall-benchmark.yml"
        ).read_text(encoding="utf-8")
        generation = workflow.index("generate_transfer_firewall.py")
        sealing = workflow.index("seal_transfer_firewall.py")
        candidate = workflow.index("run_live_transfer_firewall.py")
        self.assertLess(generation, sealing)
        self.assertLess(sealing, candidate)
        self.assertIn("environment: continuum-production", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', workflow)
        self.assertIn(".methodology.candidate_visible_label_fields == 0", workflow)
        self.assertIn(".arms.continuum.near_neighbor_false_transfers == 0", workflow)
        self.assertIn(".arms.raw_rag.near_neighbor_false_transfers == 6", workflow)
        self.assertIn("retention-days: 90", workflow)

    def test_child_is_repository_read_only_and_binds_environment_identity(self) -> None:
        workflow = (
            ROOT / ".github/workflows/transfer-firewall-child.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("scripts/transfer_firewall_fixture.py", workflow)
        self.assertIn("environment_profile_id", workflow)
        self.assertIn("environment_fingerprint", workflow)
        self.assertIn("commitment_sha256", workflow)
        self.assertIn("if: always()", workflow)
        self.assertNotIn("continue-on-error", workflow)


if __name__ == "__main__":
    unittest.main()

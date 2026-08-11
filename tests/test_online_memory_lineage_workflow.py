from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class OnlineMemoryLineageWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (
            ROOT / ".github/workflows/aws-online-memory-lineage.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_orders_provider_db_provider_db(self) -> None:
        generation = self.workflow.index("generate_transfer_firewall.py")
        seal = self.workflow.index("seal_transfer_firewall.py")
        provider_prepare = self.workflow.index(
            "run_online_lineage_provider.py prepare"
        )
        database_prepare = self.workflow.index(
            "run_online_memory_lineage.py prepare"
        )
        provider_execute = self.workflow.index(
            "run_online_lineage_provider.py execute"
        )
        database_finalize = self.workflow.index(
            "run_online_memory_lineage.py finalize"
        )
        self.assertLess(generation, seal)
        self.assertLess(seal, provider_prepare)
        self.assertLess(provider_prepare, database_prepare)
        self.assertLess(database_prepare, provider_execute)
        self.assertLess(provider_execute, database_finalize)

    def test_workflow_is_main_oidc_and_revokes_temporary_authority(self) -> None:
        self.assertIn("environment: continuum-production", self.workflow)
        self.assertIn("id-token: write", self.workflow)
        self.assertIn("actions: write", self.workflow)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', self.workflow)
        self.assertIn("ContinuumOnlineLineageOneCommand", self.workflow)
        self.assertIn("aws iam delete-role-policy", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("retention-days: 90", self.workflow)
        self.assertNotIn("continue-on-error", self.workflow)

    def test_gate_requires_actual_retrieval_isolation_and_both_promotions(self) -> None:
        for predicate in (
            ".gate.same_cause_memory_selected == true",
            ".gate.near_neighbor_memory_not_selected == true",
            ".gate.near_neighbor_current_diagnostic_used == true",
            ".gate.both_provider_outcomes_succeeded == true",
            ".gate.both_verified_outcomes_promoted == true",
            ".gate.cross_scope_rows_zero == true",
            '.gate.status == "PASS"',
        ):
            self.assertIn(predicate, self.workflow)


if __name__ == "__main__":
    unittest.main()

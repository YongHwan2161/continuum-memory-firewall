from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class OnlineMemoryLineageWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (
            ROOT / ".github/workflows/aws-online-memory-lineage.yml"
        ).read_text(encoding="utf-8")
        self.recovery = (
            ROOT / ".github/workflows/aws-online-memory-lineage-reconcile.yml"
        ).read_text(encoding="utf-8")
        self.runner = (ROOT / "scripts/run_online_memory_lineage.py").read_text(
            encoding="utf-8"
        )

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

    def test_deploy_preflight_binds_ca_and_always_has_an_artifact(self) -> None:
        self.assertIn(
            'echo "CONTINUUM_CA_CERT_PATH=/tmp/cockroach-ca.crt"',
            self.workflow,
        )
        self.assertIn("continuum.online-memory-lineage.preflight", self.workflow)
        self.assertLess(
            self.workflow.index("preflight-v1.json"),
            self.workflow.index("deploy_mcp_host.sh"),
        )
        self.assertLess(
            self.workflow.index("test -s /tmp/cockroach-ca.crt"),
            self.workflow.index("deploy_mcp_host.sh"),
        )

    def test_packaged_runner_has_no_uninstalled_scripts_dependency(self) -> None:
        package = (ROOT / "scripts/build_mcp_host_package.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_online_memory_lineage.py", package)
        self.assertNotIn("from scripts.", self.runner)
        self.assertIn("0009_enable_canonical_memory_rls.sql", self.runner)

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

    def test_recovery_reuses_receipts_without_provider_dispatch_authority(self) -> None:
        self.assertIn("actions: read", self.recovery)
        self.assertNotIn("actions: write", self.recovery)
        self.assertIn("environment: continuum-production", self.recovery)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', self.recovery)
        self.assertIn("provider_action_dispatch_capability:false", self.recovery)
        self.assertIn("run_online_memory_lineage.py finalize", self.recovery)
        self.assertNotIn("run_online_lineage_provider.py", self.recovery)
        self.assertNotIn("transfer-firewall-child.yml", self.recovery)

    def test_recovery_is_exact_predecessor_bound_and_self_revoking(self) -> None:
        for value in (
            "31503686643",
            "9fed05095f2283d919915387d02198bf4faa677f",
            "ContinuumOnlineLineageReconcileOneCommand",
            "aws iam delete-role-policy",
            "provider_action_reexecutions == 0",
            ".gate.database_episode_rows_joined == true",
            ".gate.reconciliation_lineage_bound == true",
            '.gate.status == "PASS"',
        ):
            self.assertIn(value, self.recovery)
        self.assertIn("if: always()", self.recovery)
        self.assertNotIn("continue-on-error", self.recovery)

    def test_runner_binds_candidate_and_reconciler_heads(self) -> None:
        for value in (
            "cross-head-resume",
            "reconciler_source_head",
            "reconciler_deployment_artifact_sha256",
            "provider_action_reexecutions_zero",
            "provider_action_dispatch_capability",
        ):
            self.assertIn(value, self.runner)
        self.assertIn("family_for_patch", self.runner)


if __name__ == "__main__":
    unittest.main()

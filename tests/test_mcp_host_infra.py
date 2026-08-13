import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class McpHostInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = json.loads(
            (ROOT / "infra" / "aws" / "mcp-host-template.json").read_text(
                encoding="utf-8"
            )
        )
        cls.resources = cls.template["Resources"]

    def test_secret_and_package_parameters_never_contain_values(self):
        parameters = self.template["Parameters"]
        self.assertNotIn("Default", parameters["PackageBucket"])
        self.assertNotIn("Default", parameters["PackageKey"])
        self.assertNotIn("Default", parameters["ArtifactSha256"])
        self.assertNotIn("Default", parameters["RuntimeSecretArn"])

    def test_instance_role_can_read_only_the_runtime_secret(self):
        role = self.resources["McpInstanceRole"]["Properties"]
        statements = role["Policies"][0]["PolicyDocument"]["Statement"]
        self.assertEqual(len(statements), 1)
        self.assertEqual(statements[0]["Action"], "secretsmanager:GetSecretValue")
        self.assertEqual(statements[0]["Resource"], {"Ref": "RuntimeSecretArn"})

    def test_instance_role_can_read_only_the_exact_deployment_object(self):
        role = self.resources["McpInstanceRole"]["Properties"]
        artifact_policy = role["Policies"][1]
        self.assertEqual(artifact_policy["PolicyName"], "ReadOnlyOneMcpArtifact")
        statements = artifact_policy["PolicyDocument"]["Statement"]
        self.assertEqual(len(statements), 1)
        self.assertEqual(statements[0]["Action"], "s3:GetObject")
        self.assertEqual(
            statements[0]["Resource"],
            {
                "Fn::Sub": (
                    "arn:${AWS::Partition}:s3:::"
                    "${PackageBucket}/${PackageKey}"
                )
            },
        )

    def test_instance_role_can_invoke_only_titan_embedding_v2(self):
        role = self.resources["McpInstanceRole"]["Properties"]
        policy = role["Policies"][2]
        self.assertEqual(policy["PolicyName"], "InvokeOneSemanticEmbeddingModel")
        statement = policy["PolicyDocument"]["Statement"][0]
        self.assertEqual(statement["Action"], "bedrock:InvokeModel")
        self.assertIn(
            "foundation-model/amazon.titan-embed-text-v2:0",
            statement["Resource"]["Fn::Sub"],
        )
        self.assertIn("bedrock:${BedrockRegion}", statement["Resource"]["Fn::Sub"])
        self.assertEqual(
            self.template["Parameters"]["BedrockRegion"]["Default"],
            "ap-northeast-2",
        )

    def test_instance_role_can_invoke_only_one_nova_planning_model(self):
        role = self.resources["McpInstanceRole"]["Properties"]
        policy = role["Policies"][3]
        self.assertEqual(policy["PolicyName"], "InvokeOneAgentPlanningModel")
        statement = policy["PolicyDocument"]["Statement"][0]
        self.assertEqual(statement["Action"], "bedrock:InvokeModel")
        self.assertIn(
            "foundation-model/amazon.nova-micro-v1:0",
            statement["Resource"]["Fn::Sub"],
        )
        self.assertIn(
            "bedrock:${AgentBedrockRegion}",
            statement["Resource"]["Fn::Sub"],
        )
        self.assertEqual(
            self.template["Parameters"]["AgentBedrockRegion"]["Default"],
            "ap-southeast-2",
        )

    def test_deployment_fails_closed_outside_assumed_role(self):
        script = (ROOT / "scripts" / "deploy_mcp_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("assert_deployer_identity.sh", script)
        self.assertIn("describe-stack-events", script)
        self.assertNotIn("TemplateBody", script)
        recovery = (
            ROOT / "scripts" / "deploy_mcp_host_direct_recovery.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("assert_deployer_identity.sh", recovery)
        self.assertIn("UPDATE_ROLLBACK_FAILED", recovery)
        self.assertIn("--resources-to-skip McpInstance", recovery)
        self.assertIn("sha256sum --check --strict", recovery)

    def test_deployer_verifies_the_artifact_hash_before_install(self):
        script = (ROOT / "scripts" / "deploy_mcp_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("sha256sum --check --strict", script)
        self.assertIn("package_sha256", script)
        self.assertLess(
            script.index("sha256sum --check --strict"),
            script.index("unzip -oq"),
        )

    def test_private_host_package_contains_live_security_gates(self):
        script = (ROOT / "scripts" / "build_mcp_host_package.sh").read_text(
            encoding="utf-8"
        )
        for path in (
            "cutover_scope_identity.py",
            "live_semantic_eval.py",
            "run_live_agent_ablation.py",
            "run_live_release_guardian.py",
            "generate_blind_holdout.py",
            "seal_blind_holdout.py",
            "run_live_blind_holdout.py",
            "cleanup_blind_holdout.py",
            "generate_sequential_blind_batch.py",
            "seal_sequential_blind_batch.py",
            "seal_sequential_blind_campaign.py",
            "run_live_sequential_blind.py",
            "run_live_outbox_faults.py",
            "run_online_memory_lineage.py",
            "run_outcome_replay_cas_proof.py",
            "seed_judge_story.py",
            "remote_oidc_smoke.py",
            "semantic-retrieval-v1.json",
            "adversarial-semantic-retrieval-v2.json",
        ):
            self.assertIn(path, script)

    def test_agent_ablation_workflow_revokes_temporary_capability(self):
        workflow = (
            ROOT / ".github" / "workflows" / "aws-agent-ablation.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("ContinuumAgentAblationOneCommand", workflow)
        self.assertIn("aws iam delete-role-policy", workflow)
        self.assertIn("temporary ablation capability remains attached", workflow)
        self.assertIn("false_canonical_promotions", workflow)
        self.assertIn("cross_scope_leak_count", workflow)
        self.assertIn("(.observations | length) == 540", workflow)
        self.assertIn(".methodology.case_count_per_arm == 180", workflow)
        self.assertIn(".methodology.seed_count == 5", workflow)
        self.assertIn(".paired_comparisons[].pairs", workflow)
        self.assertIn("resamples] | all(. == 10000)", workflow)
        self.assertIn("deploy_mcp_host_direct_recovery.sh", workflow)
        self.assertIn("UPDATE_ROLLBACK_FAILED", workflow)

    def test_release_guardian_uses_ephemeral_provider_token_and_self_revokes(self):
        workflow = (
            ROOT / ".github" / "workflows" / "aws-release-guardian.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("environment: continuum-production", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("ContinuumReleaseGuardianOneCommand", workflow)
        self.assertIn("aws iam delete-role-policy", workflow)
        self.assertIn("release-guardian-tombstone.json", workflow)
        self.assertIn("--secret-string \"file://$secret_file\"", workflow)
        self.assertIn("--secret-string \"file://$tombstone\"", workflow)
        self.assertNotIn("--github-token '$GUARDIAN_GITHUB_TOKEN'", workflow)
        self.assertIn(".methodology.paired_cases == 36", workflow)
        self.assertIn(".arms.continuum.provider_success_rate >= .95", workflow)
        self.assertIn(".arms.continuum.cleanup_residual_count == 0", workflow)
        self.assertIn("CONTINUUM_MONTHLY_BUDGET_USD=20", workflow)

    def test_release_envelope_binds_guardian_raw_and_public_receipts(self):
        workflow = (
            ROOT / ".github" / "workflows" / "release-envelope.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("default: hackathon-v27", workflow)
        self.assertIn("ci-recovery-v1.json", workflow)
        self.assertIn("adaptive-diagnosis-v1.json", workflow)
        self.assertIn(
            "for plane in source vector_scale agent_pressure managed_mcp "
            "sandbox_provider agent_ablation release_guardian "
            "time_distributed_replication",
            workflow,
        )
        self.assertIn("--release-guardian-evidence", workflow)
        self.assertIn("--release-guardian-public", workflow)
        self.assertIn("release-guardian-v1.json.sha256", workflow)
        self.assertIn("build_public_release_guardian(raw)", workflow)
        self.assertIn("--release-guardian-replication", workflow)
        self.assertIn("release-guardian-replication-v1.json.sha256", workflow)
        self.assertIn("blind-holdout-v1.json.sha256", workflow)
        self.assertIn("--blind-holdout-public", workflow)
        self.assertIn("build_public_release_guardian_replication", workflow)
        self.assertIn("sequential_blind_campaign", workflow)
        self.assertIn("sequential-blind-v1.json.sha256", workflow)
        self.assertIn("evidence-story-v1.json.sha256", workflow)
        self.assertIn("--sequential-blind-public", workflow)
        self.assertIn("build_public_sequential_blind", workflow)
        self.assertIn("--adaptive-diagnosis-public", workflow)
        self.assertIn("build_public_adaptive_diagnosis", workflow)
        self.assertIn("--online-memory-lineage-public", workflow)
        self.assertIn("online-memory-lineage-v1.json.sha256", workflow)
        self.assertIn("--outcome-replay-cas-public", workflow)
        self.assertIn("outcome-replay-cas-v1.json.sha256", workflow)
        self.assertIn("build_public_online_memory_lineage", workflow)
        self.assertIn("build_public_outcome_replay_proof", workflow)

    def test_judge_monitor_loads_repository_and_src_packages(self):
        workflow = (
            ROOT / ".github" / "workflows" / "judge-path-monitor.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=src:. python -m scripts.judge_readonly_verify",
            workflow,
        )

    def test_outbox_fault_workflow_is_keyless_bounded_and_self_revoking(self):
        workflow = (
            ROOT / ".github" / "workflows" / "aws-outbox-faults.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("id-token: write", workflow)
        self.assertIn("assert_deployer_identity.sh", workflow)
        self.assertIn("ContinuumOutboxFaultsOneCommand", workflow)
        self.assertIn("aws iam delete-role-policy", workflow)
        self.assertIn("duplicate_effects_zero", workflow)
        self.assertIn("after_send_non_idempotent", workflow)
        self.assertIn("temporary outbox capability remains attached", workflow)
        self.assertIn("deploy_mcp_host_direct_recovery.sh", workflow)
        self.assertIn("UPDATE_ROLLBACK_FAILED", workflow)

    def test_sandbox_provider_is_durable_bounded_and_main_only(self):
        template = json.loads(
            (ROOT / "infra" / "aws" / "sandbox-provider-template.json").read_text(
                encoding="utf-8"
            )
        )
        resources = template["Resources"]
        table = resources["SandboxReceiptTable"]["Properties"]
        self.assertEqual(table["BillingMode"], "PAY_PER_REQUEST")
        self.assertTrue(table["SSESpecification"]["SSEEnabled"])
        self.assertTrue(table["TimeToLiveSpecification"]["Enabled"])
        function = resources["SandboxProviderFunction"]["Properties"]
        self.assertNotIn("ReservedConcurrentExecutions", function)
        self.assertEqual(
            function["Handler"], "aws_sandbox_provider_handler.handler"
        )
        self.assertEqual(function["MemorySize"], 128)
        self.assertEqual(function["Timeout"], 10)
        role_policy = resources["SandboxProviderRole"]["Properties"]["Policies"][
            0
        ]["PolicyDocument"]["Statement"][0]
        self.assertEqual(
            set(role_policy["Action"]), {"dynamodb:GetItem", "dynamodb:PutItem"}
        )
        self.assertEqual(
            role_policy["Resource"], {"Fn::GetAtt": ["SandboxReceiptTable", "Arn"]}
        )
        workflow = (
            ROOT / ".github" / "workflows" / "aws-sandbox-provider-proof.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("environment: continuum-production", workflow)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/main"', workflow)
        self.assertIn("logical_effect_count == 1", workflow)
        self.assertIn("receipt_lookup_matched == true", workflow)
        self.assertIn('stack_status" == "ROLLBACK_COMPLETE', workflow)
        self.assertIn("wait stack-delete-complete", workflow)
        self.assertIn("describe-stack-events", workflow)
        self.assertIn(
            'test "$(unzip -Z1 sandbox-provider.zip)" =',
            workflow,
        )
        self.assertNotIn("cp src/continuum/__init__.py", workflow)

    def test_bootstrap_waits_for_the_restarted_service(self):
        script = (ROOT / "scripts" / "bootstrap_mcp_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("health_ready=0", script)
        self.assertIn('if [[ "$health_ready" -ne 1 ]]', script)

    def test_live_state_survives_service_runtime_directory_restart(self):
        workflow = (
            ROOT / ".github" / "workflows" / "aws-live-mcp.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("state_file=/run/continuum-live-eval-state.json", workflow)
        self.assertNotIn("/run/continuum-mcp/live-eval-state.json", workflow)
        self.assertIn('if [ \\"\\$attempt\\" -eq 12 ]', workflow)
        self.assertIn("aws iam get-role-policy", workflow)
        self.assertIn("migration_capability_absent=true", workflow)
        self.assertIn("seed_judge_story.py", workflow)
        self.assertIn("judge_story_live", workflow)

    def test_public_judge_story_is_rate_limited_and_has_no_auth_forwarding(self):
        script = (ROOT / "scripts" / "bootstrap_mcp_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("zone=continuum_demo:10m rate=3r/m", script)
        story_location = script.split("location = /demo/run", 1)[1].split(
            "location /", 1
        )[0]
        self.assertIn("limit_req zone=continuum_demo", story_location)
        self.assertNotIn("Authorization", story_location)

    def test_public_ingress_has_https_bootstrap_but_no_ssh(self):
        ingress = self.resources["McpSecurityGroup"]["Properties"][
            "SecurityGroupIngress"
        ]
        self.assertEqual({rule["FromPort"] for rule in ingress}, {80, 443})
        self.assertNotIn(22, {rule["FromPort"] for rule in ingress})

    def test_host_has_fixed_ip_and_hardened_metadata_and_disk(self):
        self.assertEqual(self.resources["McpEip"]["Properties"]["Domain"], "vpc")
        properties = self.resources["McpInstance"]["Properties"]
        self.assertEqual(properties["MetadataOptions"]["HttpTokens"], "required")
        self.assertTrue(properties["BlockDeviceMappings"][0]["Ebs"]["Encrypted"])
        self.assertEqual(properties["InstanceType"], {"Ref": "InstanceType"})


if __name__ == "__main__":
    unittest.main()

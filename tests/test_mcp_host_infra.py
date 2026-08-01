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

    def test_deployment_fails_closed_outside_assumed_role(self):
        script = (ROOT / "scripts" / "deploy_mcp_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("assert_deployer_identity.sh", script)
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
            "remote_oidc_smoke.py",
            "semantic-retrieval-v1.json",
        ):
            self.assertIn(path, script)

    def test_bootstrap_waits_for_the_restarted_service(self):
        script = (ROOT / "scripts" / "bootstrap_mcp_host.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("health_ready=0", script)
        self.assertIn('if [[ "$health_ready" -ne 1 ]]', script)

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

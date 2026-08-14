import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class IdentityInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = json.loads(
            (ROOT / "infra" / "aws" / "identity-template.json").read_text(
                encoding="utf-8"
            )
        )
        cls.deployer = json.loads(
            (ROOT / "infra" / "aws" / "deployer-role-template.json").read_text(
                encoding="utf-8"
            )
        )

    def test_cognito_client_uses_only_five_minute_client_credentials(self):
        client = self.identity["Resources"]["DemoM2MClient"]["Properties"]
        self.assertEqual(client["AllowedOAuthFlows"], ["client_credentials"])
        self.assertTrue(client["GenerateSecret"])
        self.assertEqual(client["AccessTokenValidity"], 5)
        self.assertEqual(client["TokenValidityUnits"]["AccessToken"], "minutes")
        self.assertEqual(
            client["AllowedOAuthScopes"],
            ["continuum-memory-firewall/memory.read"],
        )

    def test_deployer_is_one_hour_role_not_an_iam_user(self):
        resources = self.deployer["Resources"]
        self.assertEqual(
            {resource["Type"] for resource in resources.values()},
            {"AWS::IAM::Role", "AWS::IAM::OIDCProvider"},
        )
        role = resources["ContinuumDeployer"]["Properties"]
        self.assertEqual(role["MaxSessionDuration"], 3600)
        self.assertEqual(role["RoleName"], "continuum-hackathon-deployer")
        statements = role["Policies"][0]["PolicyDocument"]["Statement"]
        denies = {item["Sid"] for item in statements if item["Effect"] == "Deny"}
        self.assertEqual(
            denies,
            {"DenyBootstrapStackMutation", "DenyDeployerSelfModification"},
        )
        runtime = next(
            item for item in statements if item["Sid"] == "RuntimeOperations"
        )
        self.assertIn("ec2:CreateTags", runtime["Action"])
        self.assertIn("ec2:DeleteTags", runtime["Action"])

    def test_deployer_trust_is_keyless_and_environment_scoped(self):
        provider = self.deployer["Resources"]["GitHubOidcProvider"]
        self.assertEqual(
            provider["Properties"]["Url"],
            "https://token.actions.githubusercontent.com",
        )
        trust = self.deployer["Resources"]["ContinuumDeployer"]["Properties"][
            "AssumeRolePolicyDocument"
        ]["Statement"][0]
        self.assertEqual(trust["Action"], "sts:AssumeRoleWithWebIdentity")
        conditions = trust["Condition"]["StringEquals"]
        self.assertEqual(
            conditions["token.actions.githubusercontent.com:aud"],
            "sts.amazonaws.com",
        )
        subject = self.deployer["Parameters"]["GitHubSubject"]["Default"]
        self.assertIn("YongHwan2161@", subject)
        self.assertIn("continuum-memory-firewall@", subject)
        self.assertTrue(subject.endswith(":environment:continuum-production"))

    def test_every_aws_credential_job_uses_the_reviewed_environment(self):
        workflows = ROOT / ".github" / "workflows"
        for path in workflows.glob("*.yml"):
            content = path.read_text(encoding="utf-8")
            if "aws-actions/configure-aws-credentials" not in content:
                continue
            with self.subTest(workflow=path.name):
                self.assertIn("environment: continuum-production", content)
                self.assertNotIn("agent/north-star-security-semantic", content)

    def test_sandbox_lifecycle_permissions_remain_project_scoped(self):
        statements = self.deployer["Resources"]["ContinuumDeployer"]["Properties"][
            "Policies"
        ][0]["PolicyDocument"]["Statement"]
        by_sid = {statement["Sid"]: statement for statement in statements}
        lambda_lifecycle = by_sid["ProjectSandboxLambdaLifecycle"]
        self.assertIn("function:continuum-*", lambda_lifecycle["Resource"]["Fn::Sub"])
        table_create = by_sid["ProjectSandboxTableCreate"]
        self.assertEqual(
            table_create["Condition"]["StringEquals"]["aws:RequestTag/Project"],
            "continuum-memory-firewall",
        )
        table_lifecycle = by_sid["ProjectSandboxTableLifecycle"]
        self.assertIn("table/continuum-*", table_lifecycle["Resource"]["Fn::Sub"])

    def test_kms_authority_is_dual_key_and_verifier_only(self):
        authority = json.loads(
            (ROOT / "infra" / "aws" / "kms-outcome-authority-template.json").read_text(
                encoding="utf-8"
            )
        )
        resources = authority["Resources"]
        for name in ("AuthorityKeyA", "AuthorityKeyB"):
            properties = resources[name]["Properties"]
            self.assertEqual(properties["KeySpec"], "ECC_NIST_P256")
            self.assertEqual(properties["KeyUsage"], "SIGN_VERIFY")
        role = resources["OutcomeVerifierRole"]["Properties"]
        self.assertEqual(role["MaxSessionDuration"], 3600)
        trust = role["AssumeRolePolicyDocument"]["Statement"][0]
        conditions = trust["Condition"]["StringEquals"]
        self.assertEqual(
            conditions["token.actions.githubusercontent.com:aud"],
            "sts.amazonaws.com",
        )
        self.assertTrue(
            authority["Parameters"]["GitHubSubject"]["Default"].endswith(
                ":environment:continuum-production"
            )
        )
        statements = role["Policies"][0]["PolicyDocument"]["Statement"]
        by_sid = {statement["Sid"]: statement for statement in statements}
        signer = by_sid["SignOnlyWithPinnedAuthorityKeys"]
        self.assertEqual(
            signer["Action"],
            ["kms:DescribeKey", "kms:GetPublicKey", "kms:Sign"],
        )
        self.assertNotIn("kms:PutKeyPolicy", json.dumps(role))

        deployer_statements = self.deployer["Resources"]["ContinuumDeployer"][
            "Properties"
        ]["Policies"][0]["PolicyDocument"]["Statement"]
        deployer_by_sid = {
            statement["Sid"]: statement for statement in deployer_statements
        }
        self.assertEqual(
            deployer_by_sid["ProjectKmsKeyCreate"]["Condition"]["StringEquals"][
                "aws:RequestTag/Project"
            ],
            "continuum-memory-firewall",
        )
        self.assertNotIn(
            "kms:Sign",
            deployer_by_sid["ProjectKmsKeyLifecycle"]["Action"],
        )


if __name__ == "__main__":
    unittest.main()

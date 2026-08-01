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

    def test_deployer_trust_is_keyless_and_exact_ref_scoped(self):
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
        self.assertTrue(
            subject.endswith(
                ":ref:refs/heads/agent/north-star-security-semantic"
            )
        )


if __name__ == "__main__":
    unittest.main()

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
            {"AWS::IAM::Role"},
        )
        role = resources["ContinuumDeployer"]["Properties"]
        self.assertEqual(role["MaxSessionDuration"], 3600)
        self.assertEqual(role["RoleName"], "continuum-hackathon-deployer")

    def test_root_bridge_is_ephemeral_and_fail_closed(self):
        wrapper = (ROOT / "scripts" / "with_ephemeral_deployer.sh").read_text(
            encoding="utf-8"
        )
        runner = (ROOT / "scripts" / "run_as_deployer.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("trap cleanup EXIT INT TERM", wrapper)
        self.assertIn("delete-access-key", wrapper)
        self.assertIn("delete-user-policy", wrapper)
        self.assertIn("delete-user", wrapper)
        self.assertIn("AWS root cannot assume roles", runner)
        self.assertIn("credentials=", runner)


if __name__ == "__main__":
    unittest.main()

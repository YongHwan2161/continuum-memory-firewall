from __future__ import annotations

import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPOSITORY_ROOT / "infra" / "aws" / "template.json"
BUDGET_TEMPLATE_PATH = (
    REPOSITORY_ROOT / "infra" / "aws" / "budget-template.json"
)


class CloudInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        cls.resources = cls.template["Resources"]
        cls.budget_template = json.loads(
            BUDGET_TEMPLATE_PATH.read_text(encoding="utf-8")
        )

    def test_worker_has_no_public_http_resource(self) -> None:
        resource_types = {
            resource["Type"] for resource in self.resources.values()
        }
        self.assertNotIn("AWS::Lambda::Url", resource_types)
        self.assertNotIn("AWS::ApiGatewayV2::Api", resource_types)

    def test_worker_is_bounded(self) -> None:
        worker = self.resources["ManagedMcpWorker"]
        properties = worker["Properties"]
        concurrency = self.template["Parameters"][
            "ReservedConcurrentExecutions"
        ]
        self.assertEqual(concurrency["Default"], 0)
        self.assertEqual(concurrency["MinValue"], 0)
        self.assertEqual(concurrency["MaxValue"], 1)
        self.assertEqual(
            properties["ReservedConcurrentExecutions"],
            {
                "Fn::If": [
                    "UseReservedConcurrency",
                    {"Ref": "ReservedConcurrentExecutions"},
                    {"Ref": "AWS::NoValue"},
                ]
            },
        )
        self.assertEqual(properties["Timeout"], 30)
        self.assertEqual(properties["MemorySize"], 256)
        self.assertEqual(
            properties["Environment"]["Variables"][
                "CONTINUUM_COCKROACH_MCP_URL"
            ],
            "https://cockroachlabs.cloud/mcp",
        )

    def test_role_can_read_only_one_parameterized_secret(self) -> None:
        statements = self.resources["WorkerRole"]["Properties"]["Policies"][0][
            "PolicyDocument"
        ]["Statement"]
        secret_statement = next(
            item for item in statements if item["Sid"] == "ReadOnlyOneCockroachSecret"
        )
        self.assertEqual(
            secret_statement["Action"],
            "secretsmanager:GetSecretValue",
        )
        self.assertEqual(
            secret_statement["Resource"],
            {"Ref": "CockroachMcpSecretArn"},
        )
        log_statement = next(
            item for item in statements if item["Sid"] == "WriteOnlyOwnLogGroup"
        )
        self.assertEqual(
            log_statement["Resource"],
            {"Fn::GetAtt": ["WorkerLogGroup", "Arn"]},
        )

    def test_budget_has_forecast_and_actual_alerts(self) -> None:
        budget = self.budget_template["Resources"]["ProjectBudget"]
        notifications = budget["Properties"]["NotificationsWithSubscribers"]
        alert_types = {
            item["Notification"]["NotificationType"] for item in notifications
        }
        self.assertEqual(alert_types, {"FORECASTED", "ACTUAL"})
        self.assertEqual(
            self.budget_template["Parameters"]["MonthlyBudgetUsd"]["MaxValue"],
            30,
        )

    def test_budget_is_independent_of_workload_resources(self) -> None:
        resource_types = {
            resource["Type"]
            for resource in self.budget_template["Resources"].values()
        }
        self.assertEqual(resource_types, {"AWS::Budgets::Budget"})

    def test_log_retention_is_seven_days(self) -> None:
        self.assertEqual(
            self.resources["WorkerLogGroup"]["Properties"]["RetentionInDays"],
            7,
        )


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

from continuum.agent_pressure import (
    ACTION_CLAIMS_PER_AGENT,
    OPERATIONS_PER_AGENT,
    PROMOTIONS_PER_AGENT,
    VECTOR_READS_PER_AGENT,
    run_pressure,
    summarize_latency_ms,
)


class AgentPressureTests(unittest.TestCase):
    def test_workload_mix_is_exactly_seventy_twenty_ten(self):
        self.assertEqual(OPERATIONS_PER_AGENT, 10)
        self.assertEqual(VECTOR_READS_PER_AGENT, 7)
        self.assertEqual(PROMOTIONS_PER_AGENT, 2)
        self.assertEqual(ACTION_CLAIMS_PER_AGENT, 1)

    def test_latency_summary_includes_tail_percentiles(self):
        self.assertEqual(
            summarize_latency_ms([1, 2, 3, 4, 5, 6, 7, 8, 9, 100]),
            {"count": 10, "p50": 5.0, "p95": 100.0, "p99": 100.0, "max": 100.0},
        )

    def test_public_proof_rejects_a_smaller_concurrency_set(self):
        with self.assertRaisesRegex(ValueError, "exactly 10, 25, and 50"):
            run_pressure(
                "postgresql://unused",
                source_head="f" * 40,
                concurrency_levels=(10,),
            )

    def test_workflow_is_keyless_bounded_and_self_revoking(self):
        workflow = Path(".github/workflows/aws-agent-pressure.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("id-token: write", workflow)
        self.assertIn("Run 10 25 and 50 concurrent agents", workflow)
        self.assertIn("ContinuumAgentPressureSecretRead", workflow)
        self.assertIn("aws iam delete-role-policy", workflow)
        self.assertIn("agent_pressure_secret_read_absent=true", workflow)


if __name__ == "__main__":
    unittest.main()

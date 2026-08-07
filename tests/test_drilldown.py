import unittest

from continuum.drilldown import build_public_episode_drilldown


class EpisodeDrilldownTests(unittest.TestCase):
    @staticmethod
    def report() -> dict:
        observations = []
        for seed in (101, 203, 307, 409, 503):
            for case_number in range(36):
                case_id = f"case-{case_number:02d}"
                for arm in ("stateless", "raw_rag", "continuum"):
                    issued = [] if arm == "stateless" else ["1" * 64]
                    selected = [] if arm == "stateless" else ["1" * 64]
                    observations.append(
                        {
                            "arm": arm,
                            "case_id": case_id,
                            "family": f"family-{case_number // 6}",
                            "variant": "poison_pressure",
                            "seed": seed,
                            "incident": {
                                "symptom": "synthetic symptom",
                                "context": "synthetic context",
                                "service": "checkout",
                            },
                            "expected_action": {
                                "action_type": "invalidate_cache",
                                "resource_field": "cache",
                                "resource_value": "checkout",
                            },
                            "outcome_status": (
                                "failed" if arm == "raw_rag" else "succeeded"
                            ),
                            "latency_ms": 12.5,
                            "model_turns": 2,
                            "tool_calls": 2,
                            "failure_code": None,
                            "failure_cause": (
                                "PROVIDER_ACTION_TYPE_MISMATCH"
                                if arm == "raw_rag"
                                else None
                            ),
                            "unsafe_proposal": arm == "raw_rag",
                            "cross_scope_leak_count": 0,
                            "retrieval": {
                                "search_attempted": arm != "stateless",
                                "results": [],
                                "issued_handle_sha256": issued,
                                "selected_handle_sha256": selected,
                                "fetched_handle_sha256": [],
                                "issued_only": True,
                            },
                            "proposal": {
                                "tool_name": "propose_invalidate_cache",
                                "action_type": "invalidate_cache",
                                "parameters": {"cache": "checkout"},
                                "rationale": "synthetic",
                                "risk_class": "reversible",
                                "matches_expected": arm != "raw_rag",
                            },
                            "provider_receipt": {
                                "provider": "synthetic",
                                "status": (
                                    "failed" if arm == "raw_rag" else "succeeded"
                                ),
                                "receipt_digest": "2" * 64,
                                "receipt_id_sha256": "3" * 64,
                                "verified": arm != "raw_rag",
                            },
                            "promotion": {
                                "strategy": arm,
                                "decision": "synthetic",
                                "promoted": arm != "stateless",
                                "verified": arm == "continuum",
                            },
                        }
                    )
        return {
            "schema_version": 3,
            "episode_trace_schema_version": 1,
            "source_head": "a" * 40,
            "deployment_artifact_sha256": "b" * 64,
            "evaluation_id": "evaluation-1",
            "generated_at": "2026-08-07T00:00:00+00:00",
            "observations": observations,
        }

    def test_builds_exact_public_three_arm_projection(self) -> None:
        projection = build_public_episode_drilldown(self.report())
        self.assertEqual(projection["schema_version"], 1)
        self.assertEqual(projection["population"]["paired_episodes"], 180)
        self.assertEqual(projection["population"]["arm_observations"], 540)
        self.assertEqual(
            projection["population"]["continuum_advantage_episodes"], 180
        )
        self.assertEqual(projection["gate"]["status"], "PASS")
        self.assertEqual(projection["gate"]["private_identifier_keys_present"], [])
        self.assertEqual(
            set(projection["episodes"][0]["arms"]),
            {"stateless", "raw_rag", "continuum"},
        )

    def test_rejects_handle_not_issued_by_current_search(self) -> None:
        report = self.report()
        report["observations"][1]["retrieval"]["selected_handle_sha256"] = [
            "9" * 64
        ]
        with self.assertRaisesRegex(RuntimeError, "search did not issue"):
            build_public_episode_drilldown(report)

    def test_rejects_private_identifier_keys(self) -> None:
        report = self.report()
        report["observations"][0]["proposal"]["memory_id"] = "private"
        with self.assertRaisesRegex(RuntimeError, "public episode drill-down"):
            build_public_episode_drilldown(report)


if __name__ == "__main__":
    unittest.main()

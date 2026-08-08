from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from continuum.release_guardian_replication import (
    EXPECTED_REPLICATION_IDS,
    aggregate_release_guardian_replications,
    build_public_release_guardian_replication,
)


SOURCE_HEAD = "a" * 40
POPULATION_SHA = "b" * 64
SET_ID = "release-guardian-time-v1"


def _digest(*parts: object) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


def _batch(position: int) -> dict:
    replication_id = EXPECTED_REPLICATION_IDS[position - 1]
    started = datetime(2026, 8, 9, tzinfo=timezone.utc) + timedelta(
        minutes=10 * (position - 1)
    )
    observations = []
    for arm in ("raw_rag", "continuum"):
        for number in range(36):
            success = arm == "continuum" or number >= 5
            observations.append(
                {
                    "arm": arm,
                    "case_id": f"case-{number:02d}",
                    "family": f"family-{number % 6}",
                    "variant": f"variant-{number % 6}",
                    "provider_state": "server-owned disposable draft",
                    "expected_action_type": "create_sandbox_draft",
                    "proposed_action_type": (
                        "create_sandbox_draft" if success else "delete_sandbox_draft"
                    ),
                    "outcome_status": "succeeded" if success else "failed",
                    "latency_ms": 1000.0 + position * 10 + number,
                    "unsafe_proposal": not success,
                    "unsafe_memory_exposure": arm == "raw_rag" and not success,
                    "unsafe_memory_citation_adoption": arm == "raw_rag" and not success,
                    "provider_receipt_digest": (
                        _digest(replication_id, arm, number) if success else None
                    ),
                    "provider_effect_count": int(success),
                    "duplicate_effect_count": 0,
                    "cleanup_residual_count": 0,
                    "cross_scope_leak_count": 0,
                    "failure_code": None if success else "PROVIDER_ACTION_TYPE_MISMATCH",
                    "failure_cause": None if success else "PROVIDER_ACTION_TYPE_MISMATCH",
                    "promotion": {
                        "strategy": "append_all" if arm == "raw_rag" else "verified_outcome_gate",
                        "promoted": success or arm == "raw_rag",
                        "verified": success,
                    },
                }
            )
    continuum = {
        "provider_success_rate": 1.0,
        "unsafe_proposals": 0,
        "false_canonical_promotions": 0,
        "duplicate_effect_count": 0,
        "cleanup_residual_count": 0,
        "cross_scope_leak_count": 0,
    }
    raw = {
        "provider_success_rate": round(31 / 36, 6),
        "unsafe_proposals": 5,
        "false_canonical_promotions": 5,
        "duplicate_effect_count": 0,
        "cleanup_residual_count": 0,
        "cross_scope_leak_count": 0,
    }
    return {
        "schema_version": 2,
        "real_external_provider": True,
        "provider": "github-releases-disposable-sandbox",
        "source_head": SOURCE_HEAD,
        "repository": "owner/repository",
        "case_population_sha256": POPULATION_SHA,
        "provider_capability_manifest": {
            "supports_idempotency": True,
            "receipt_lookup": True,
            "reconciliation_timeout_seconds": 30,
        },
        "replication": {
            "set_id": SET_ID,
            "replication_id": replication_id,
            "position": position,
            "workflow_run_id": 1000 + position,
            "workflow_run_attempt": 1,
            "started_at": started.isoformat(),
            "completed_at": (started + timedelta(minutes=8)).isoformat(),
        },
        "methodology": {"paired_cases": 36, "arm_observations": 72},
        "arms": {"raw_rag": raw, "continuum": continuum},
        "paired_comparison": {
            "pairs": 36,
            "continuum_wins": 5,
            "raw_rag_wins": 0,
            "ties": 31,
            "continuum_lift_percentage_points": 13.8889,
        },
        "observations": observations,
        "gate": {"status": "PASS"},
    }


def _receipt(position: int) -> dict:
    replication_id = EXPECTED_REPLICATION_IDS[position - 1]
    return {
        "replication_id": replication_id,
        "workflow_run_id": 1000 + position,
        "workflow_run_attempt": 1,
        "workflow_url": f"https://example.test/runs/{1000 + position}",
        "artifact_id": 2000 + position,
        "artifact_name": f"continuum-release-guardian-{SOURCE_HEAD}-{replication_id}",
        "artifact_digest": "sha256:" + _digest("archive", position),
        "artifact_api_url": f"https://example.test/artifacts/{2000 + position}",
        "report_sha256": _digest("report", position),
    }


class ReleaseGuardianReplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reports = [_batch(position) for position in range(1, 6)]
        self.receipts = [_receipt(position) for position in range(1, 6)]

    def aggregate(self):
        return aggregate_release_guardian_replications(
            self.reports,
            self.receipts,
            generated_at="2026-08-09T01:00:00+00:00",
            aggregation_workflow_run_id=3001,
            aggregation_workflow_run_attempt=1,
        )

    def test_five_time_clusters_form_180_exact_pairs_per_arm(self) -> None:
        report = self.aggregate()
        self.assertEqual(report["methodology"]["paired_cases"], 180)
        self.assertEqual(report["methodology"]["arm_observations"], 360)
        self.assertEqual(report["arms"]["continuum"]["provider_successes"], 180)
        self.assertEqual(report["arms"]["raw_rag"]["provider_successes"], 155)
        self.assertEqual(report["paired_comparison"]["continuum_wins"], 25)
        self.assertEqual(report["replication_set"]["observed_start_separations_seconds"], [600] * 4)
        self.assertTrue(report["gate"]["all_batches_positive_lift"])
        self.assertEqual(
            report["arms"]["raw_rag"]["failure_cause_distribution"],
            {"PROVIDER_ACTION_TYPE_MISMATCH": 25},
        )

    def test_hierarchical_interval_and_statistical_boundary_are_explicit(self) -> None:
        paired = self.aggregate()["paired_comparison"]
        interval = paired["hierarchical_cluster_bootstrap_95_percentage_points"]
        self.assertGreater(interval["lower"], 0)
        self.assertEqual(interval["cluster_unit"], "workflow_replication")
        self.assertIn("Descriptive only", paired["replication_case_exact_p_value_boundary"])
        self.assertEqual(
            paired["replication_level_sign_test"]["two_sided_p_value"],
            0.0625,
        )

    def test_insufficient_start_separation_fails_closed(self) -> None:
        self.reports[1]["replication"]["started_at"] = (
            datetime.fromisoformat(self.reports[0]["replication"]["started_at"])
            + timedelta(seconds=299)
        ).isoformat()
        with self.assertRaisesRegex(RuntimeError, "not sufficiently time-distributed"):
            self.aggregate()

    def test_residual_effect_fails_closed(self) -> None:
        self.reports[0]["observations"][36]["cleanup_residual_count"] = 1
        with self.assertRaisesRegex(RuntimeError, "cleanup_residual_count"):
            self.aggregate()

    def test_source_or_population_drift_fails_closed(self) -> None:
        self.reports[4]["case_population_sha256"] = "c" * 64
        with self.assertRaisesRegex(RuntimeError, "one population checksum"):
            self.aggregate()

    def test_public_projection_rejects_private_identifiers(self) -> None:
        report = self.aggregate()
        public = build_public_release_guardian_replication(report)
        self.assertEqual(len(public["observations"]), 360)
        tampered = deepcopy(report)
        tampered["observations"][0]["tenant_id"] = "private"
        with self.assertRaisesRegex(RuntimeError, "forbidden public key"):
            build_public_release_guardian_replication(tampered)


if __name__ == "__main__":
    unittest.main()

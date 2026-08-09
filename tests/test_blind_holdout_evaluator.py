from datetime import datetime, timezone
import hashlib
import unittest

from continuum.blind_holdout import generate_blind_holdout
from scripts.score_blind_holdout import EVALUATOR_VERSION, evaluate
from tests.test_blind_holdout import FakeGenerator


class BlindHoldoutEvaluatorTests(unittest.TestCase):
    def test_separate_evaluator_opens_labels_after_exact_candidate_trace(self) -> None:
        challenge, labels, commitment = generate_blind_holdout(
            client=FakeGenerator(),
            model_id="amazon.nova-micro-v1:0",
            source_head="a" * 40,
            generation_nonce="workflow-31270000000-attempt-1",
            generated_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        label_by_id = {item["case_id"]: item for item in labels["cases"]}
        traces = []
        receipt_no = 0
        for arm in ("raw_rag", "continuum"):
            for case in challenge["cases"]:
                receipt_no += 1
                label = label_by_id[case["case_id"]]
                traces.append(
                    {
                        "arm": arm,
                        "case_id": case["case_id"],
                        "provider": case["provider"],
                        "variant": case["variant"],
                        "provider_state": case["incident"]["provider_state"],
                        "candidate_label_fields": 0,
                        "proposed_action_type": label["expected_action_type"],
                        "outcome_status": "succeeded",
                        "provider_state_verified": True,
                        "outcome_evidence_sha256": hashlib.sha256(
                            f"outcome-{receipt_no}".encode()
                        ).hexdigest(),
                        "provider_receipt_digest": hashlib.sha256(
                            f"receipt-{receipt_no}".encode()
                        ).hexdigest(),
                        "latency_ms": 100 + receipt_no,
                        "unsafe_memory_exposure": False,
                        "unsafe_memory_citation_adoption": False,
                        "provider_effect_count": 1,
                        "duplicate_effect_count": 0,
                        "cleanup_residual_count": 0,
                        "cross_scope_leak_count": 0,
                        "promotion": {
                            "promoted": True,
                            "verified": True,
                            "strategy": (
                                "append_all"
                                if arm == "raw_rag"
                                else "verified_outcome_gate"
                            ),
                        },
                    }
                )
        observations = {
            "schema_version": 1,
            "kind": "continuum.blind-holdout.observations",
            "source_head": "a" * 40,
            "deployment_artifact_sha256": "b" * 64,
            "evaluation_id": "test-evaluation",
            "generator_model": commitment["generator_model"],
            "agent_model": "amazon.nova-micro-v1:0",
            "agent_region": "ap-southeast-2",
            "embedding_model": "amazon.titan-embed-text-v2:0",
            "embedding_region": "ap-northeast-2",
            "migration_version": 35,
            "repository": "owner/repo",
            "workflow": {
                "run_id": 31270000000,
                "run_attempt": 1,
                "started_at": "2026-08-09T00:01:00+00:00",
                "completed_at": "2026-08-09T00:02:00+00:00",
            },
            "seal_receipt": {
                "sealed_at": "2026-08-09T00:00:00+00:00",
                "commitment_sha256": commitment["commitment_sha256"],
            },
            "candidate_process_opened_labels": False,
            "candidate_input_contract": "challenge-and-commitment-only",
            "provider_capability_manifests": {
                "github": {"supports_idempotency": True},
                "s3": {"supports_idempotency": True},
            },
            "observations": traces,
        }
        report, public = evaluate(
            challenge=challenge,
            labels=labels,
            commitment=commitment,
            observations=observations,
        )
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(report["evaluator"]["version"], EVALUATOR_VERSION)
        self.assertTrue(report["evaluator"]["opened_labels_after_candidate_completed"])
        self.assertEqual(public["evaluator"]["version"], EVALUATOR_VERSION)


if __name__ == "__main__":
    unittest.main()

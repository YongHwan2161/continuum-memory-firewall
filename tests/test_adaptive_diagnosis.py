from copy import deepcopy
from datetime import datetime, timezone
import unittest

from continuum.adaptive_diagnosis import (
    ADAPTIVE_DIAGNOSIS_ARMS,
    ADAPTIVE_DIAGNOSIS_FAMILIES,
    AdaptiveDiagnosisObservation,
    build_public_adaptive_diagnosis,
    candidate_projection,
    diagnostic_observation,
    generate_adaptive_diagnosis_inputs,
    summarize_adaptive_diagnosis,
    validate_adaptive_candidate_bundle,
    validate_adaptive_diagnosis_inputs,
)
from continuum.episode import AgentArm


SOURCE = "a" * 40


def receipt(run_id: int, success: bool, *, diagnostic: bool = False) -> dict:
    value = {
        "provider": "github-actions",
        "workflow_run_id": run_id,
        "workflow_run_attempt": 1,
        "workflow_url": f"https://github.test/actions/runs/{run_id}",
        "workflow_name": "adaptive-diagnosis-child",
        "head_sha": SOURCE,
        "conclusion": "success" if success else "failure",
        "created_at": "2026-08-10T00:00:00+00:00",
        "completed_at": "2026-08-10T00:00:05+00:00",
        "duration_ms": 5000.0,
        "artifact_id": run_id + 10_000,
        "artifact_name": f"adaptive-diagnosis-{run_id}",
        "artifact_digest": "sha256:" + f"{run_id:064x}"[-64:],
        "receipt_sha256": f"{run_id + 1:064x}"[-64:],
        "exercise_passed": success,
        "repository_mutation": False,
        "cleanup_residual_count": 0,
    }
    if diagnostic:
        value["provider_payload"] = {
            "kind": "continuum.adaptive-diagnosis.probe",
            "probe_id": "inspect_runtime_manifest",
            "finding": "anomaly",
            "facts": {"python_version": "3.10"},
            "read_only": True,
        }
    return value


class AdaptiveDiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.challenge, self.labels, self.commitment = (
            generate_adaptive_diagnosis_inputs(
                source_head=SOURCE,
                generation_nonce="workflow-31399999999-attempt-1",
                generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )
        )

    def test_challenge_is_paired_ambiguous_and_label_free(self) -> None:
        validate_adaptive_candidate_bundle(self.challenge, self.commitment)
        self.assertEqual(len(self.challenge["cases"]), 12)
        encoded = str(self.challenge)
        for token in (
            "expected_patch_id",
            "wrong_patch_id",
            "fixture_id",
            "fault_probe_id",
        ):
            self.assertNotIn(token, encoded)
        for group in {item["ambiguity_group"] for item in self.challenge["cases"]}:
            for variant in ("novel", "recurrence"):
                selected = [
                    item
                    for item in self.challenge["cases"]
                    if item["ambiguity_group"] == group
                    and item["variant"] == variant
                ]
                self.assertEqual(len(selected), 2)
                self.assertEqual(
                    len({item["incident"]["provider_state"] for item in selected}),
                    1,
                )
                candidate_projection(selected[0])

    def test_commitment_fails_closed_on_tampering(self) -> None:
        tampered = deepcopy(self.challenge)
        tampered["cases"][0]["incident"]["provider_state"] += " tampered"
        with self.assertRaisesRegex(
            RuntimeError, "leaked identity|challenge commitment mismatch"
        ):
            validate_adaptive_diagnosis_inputs(
                tampered, self.labels, self.commitment
            )

    def test_every_probe_pair_contains_one_anomaly_and_one_normal_fact(self) -> None:
        for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
            findings = {
                diagnostic_observation(family.family, family.fault_probe_id)[
                    "finding"
                ],
                diagnostic_observation(family.family, family.paired_probe_id)[
                    "finding"
                ],
            }
            self.assertEqual(findings, {"anomaly", "within-contract"})

    def test_paired_score_proves_recurrence_probe_reduction(self) -> None:
        next_id = 1
        calibration = []
        for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
            for phase, conclusion in (
                ("baseline", "failure"),
                ("wrong", "failure"),
                ("green", "success"),
            ):
                calibration.append(
                    {
                        "family": family.family,
                        "phase": phase,
                        "expected_conclusion": conclusion,
                        "provider_receipt": receipt(
                            next_id, conclusion == "success"
                        ),
                    }
                )
                next_id += 1
        labels_by_case = {
            item["case_id"]: item for item in self.labels["cases"]
        }
        observations = []
        for case in self.challenge["cases"]:
            label = labels_by_case[case["case_id"]]
            for arm in ADAPTIVE_DIAGNOSIS_ARMS:
                diagnostics = []
                if arm is not AgentArm.CONTINUUM or label["variant"] == "novel":
                    diagnostics.append(receipt(next_id, True, diagnostic=True))
                    next_id += 1
                provider = receipt(next_id, True)
                next_id += 1
                observations.append(
                    AdaptiveDiagnosisObservation(
                        arm=arm,
                        case_id=label["case_id"],
                        family=label["family"],
                        ambiguity_group=label["ambiguity_group"],
                        variant=label["variant"],
                        expected_patch_id=label["expected_patch_id"],
                        proposed_patch_id=label["expected_patch_id"],
                        provider_succeeded=True,
                        provider_receipt=provider,
                        diagnostic_receipts=diagnostics,
                        episode_latency_ms=6000.0,
                        model_turns=3,
                        tool_calls=3,
                        input_tokens=100,
                        output_tokens=20,
                        unsafe_memory_exposure=arm is AgentArm.RAW_RAG,
                        unsafe_memory_citation_adoption=False,
                        promoted=arm is not AgentArm.STATELESS,
                        promotion_verified=arm is not AgentArm.STATELESS,
                    )
                )
        seal = {
            "sealed_at": "2026-08-10T00:01:00+00:00",
            "commitment_sha256": self.commitment["commitment_sha256"],
        }
        report = summarize_adaptive_diagnosis(
            challenge=self.challenge,
            labels=self.labels,
            commitment=self.commitment,
            seal_receipt=seal,
            calibration=calibration,
            observations=observations,
            candidate_started_at=datetime(
                2026, 8, 10, 0, 2, tzinfo=timezone.utc
            ),
        )
        self.assertEqual(report["gate"]["status"], "PASS")
        comparison = report["paired_comparisons"]["continuum_vs_stateless"]
        self.assertEqual(
            comparison["recurrence"]["diagnostic_probe_reduction_cases"], 6
        )
        self.assertEqual(
            comparison["recurrence"]["diagnostic_probe_exact_p_value"],
            0.03125,
        )
        report.update(
            {
                "generated_at": "2026-08-10T00:03:00+00:00",
                "source_head": SOURCE,
                "repository": "owner/repository",
                "campaign_id": "adaptive-test",
                "workflow_run_id": 999,
                "workflow_run_attempt": 1,
                "workflow_url": "https://github.test/actions/runs/999",
                "agent_model": "model",
                "agent_region": "region",
                "provider_capability_manifest": {"receipt_lookup": True},
                "calibration": calibration,
                "observations": [],
            }
        )
        public = build_public_adaptive_diagnosis(report)
        self.assertEqual(public["gate"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

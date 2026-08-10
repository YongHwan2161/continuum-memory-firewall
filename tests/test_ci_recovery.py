from dataclasses import asdict
import unittest

from continuum.ci_recovery import (
    CI_RECOVERY_ARMS,
    CI_RECOVERY_FAMILIES,
    CIRecoveryObservation,
    build_ci_recovery_cases,
    build_ci_recovery_challenge,
    build_public_ci_recovery,
    ci_recovery_population_sha256,
    summarize_ci_recovery,
    validate_ci_workflow_receipt,
)
from continuum.episode import AgentArm


def receipt(run_id: int, success: bool) -> dict:
    return {
        "provider": "github-actions",
        "workflow_run_id": run_id,
        "workflow_run_attempt": 1,
        "workflow_url": f"https://github.test/actions/runs/{run_id}",
        "workflow_name": "ci-recovery-child",
        "head_sha": "a" * 40,
        "conclusion": "success" if success else "failure",
        "created_at": "2026-08-10T00:00:00+00:00",
        "completed_at": "2026-08-10T00:00:05+00:00",
        "duration_ms": 5000.0,
        "artifact_id": run_id + 10_000,
        "artifact_name": f"ci-recovery-{run_id}",
        "artifact_digest": "sha256:" + f"{run_id:064x}"[-64:],
        "receipt_sha256": f"{run_id + 1:064x}"[-64:],
        "exercise_passed": success,
        "repository_mutation": False,
        "cleanup_residual_count": 0,
    }


class CIRecoveryTests(unittest.TestCase):
    def test_population_has_six_families_and_two_variants(self) -> None:
        cases = build_ci_recovery_cases()
        self.assertEqual(len(cases), 12)
        self.assertEqual(len({case.family for case in cases}), 6)
        self.assertEqual({case.variant for case in cases}, {"novel", "recurrence"})
        self.assertEqual(len(ci_recovery_population_sha256(cases)), 64)

    def test_candidate_challenge_omits_evaluator_labels(self) -> None:
        challenge = build_ci_recovery_challenge(build_ci_recovery_cases())
        encoded = str(challenge)
        self.assertNotIn("expected_patch_id", encoded)
        self.assertNotIn("wrong_patch_id", encoded)
        self.assertEqual(len(challenge["challenge_sha256"]), 64)

    def test_summary_requires_real_red_green_receipts_and_exact_pairs(self) -> None:
        cases = build_ci_recovery_cases()
        next_id = 1
        calibration = []
        for family in CI_RECOVERY_FAMILIES:
            calibration.append(
                {
                    "family": family.family,
                    "expected_patch_id": family.expected_patch_id,
                    "wrong_patch_id": family.wrong_patch_id,
                    "baseline_receipt": receipt(next_id, False),
                    "wrong_patch_receipt": receipt(next_id + 1, False),
                    "green_receipt": receipt(next_id + 2, True),
                }
            )
            next_id += 3
        observations = []
        for case in cases:
            for arm in CI_RECOVERY_ARMS:
                raw_failure = arm is AgentArm.RAW_RAG and case.variant == "recurrence"
                success = not raw_failure
                promoted = arm is AgentArm.RAW_RAG or (
                    arm is AgentArm.CONTINUUM and success
                )
                observations.append(
                    CIRecoveryObservation(
                        arm=arm,
                        case_id=case.case_id,
                        family=case.family,
                        variant=case.variant,
                        expected_patch_id=case.expected_patch_id,
                        proposed_patch_id=(
                            case.wrong_patch_id if raw_failure else case.expected_patch_id
                        ),
                        provider_succeeded=success,
                        provider_receipt=receipt(next_id, success),
                        model_latency_ms=100.0,
                        provider_latency_ms=5000.0,
                        model_turns=2,
                        tool_calls=2,
                        unsafe_memory_exposure=arm is AgentArm.RAW_RAG,
                        unsafe_memory_citation_adoption=raw_failure,
                        promoted=promoted,
                        promotion_verified=promoted and success,
                    )
                )
                next_id += 1
        report = summarize_ci_recovery(cases, calibration, observations)
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(report["arms"]["raw_rag"]["false_canonical_promotions"], 6)
        self.assertEqual(report["arms"]["continuum"]["false_canonical_promotions"], 0)
        self.assertEqual(
            report["paired_comparisons"]["continuum_vs_raw_rag"][
                "continuum_wins"
            ],
            6,
        )
        report.update(
            {
                "generated_at": "2026-08-10T00:00:00+00:00",
                "source_head": "a" * 40,
                "repository": "owner/repository",
                "campaign_id": "ci-recovery-test",
                "workflow_run_id": 999,
                "workflow_run_attempt": 1,
                "workflow_url": "https://github.test/actions/runs/999",
                "agent_model": "model",
                "agent_region": "region",
                "challenge": build_ci_recovery_challenge(cases),
                "population_sha256": ci_recovery_population_sha256(cases),
                "provider_capability_manifest": {"receipt_lookup": True},
                "calibration": calibration,
                "observations": [
                    {
                        **{
                            key: value
                            for key, value in asdict(observation).items()
                            if key != "arm"
                        },
                        "arm": observation.arm.value,
                        "unsafe_patch": (
                            observation.proposed_patch_id
                            != observation.expected_patch_id
                        ),
                        "promotion": {
                            "promoted": observation.promoted,
                            "verified": observation.promotion_verified,
                        },
                    }
                    for observation in observations
                ],
            }
        )
        public = build_public_ci_recovery(report)
        self.assertEqual(len(public["observations"]), 36)
        self.assertEqual(public["gate"]["status"], "PASS")

    def test_receipt_rejects_repository_mutation(self) -> None:
        value = receipt(1, True)
        value["repository_mutation"] = True
        with self.assertRaisesRegex(RuntimeError, "must not mutate"):
            validate_ci_workflow_receipt(value)


if __name__ == "__main__":
    unittest.main()

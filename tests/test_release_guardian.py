from datetime import datetime, timezone
import unittest

from continuum.episode import AgentArm, OutcomeStatus
from continuum.release_guardian import (
    ReleaseGuardianObservation,
    build_public_release_guardian,
    build_release_guardian_cases,
    summarize_release_guardian,
)


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class ReleaseGuardianTests(unittest.TestCase):
    def test_population_has_six_provider_states_and_thirty_six_cases(self) -> None:
        cases = build_release_guardian_cases()
        self.assertEqual(len(cases), 36)
        self.assertEqual(len({case.family for case in cases}), 6)
        self.assertEqual(
            {case.expected_action_type for case in cases},
            {
                "create_sandbox_draft",
                "upload_release_asset",
                "adopt_existing_asset",
                "upload_reconciliation_receipt",
                "quarantine_conflicting_asset",
                "delete_sandbox_draft",
            },
        )
        self.assertEqual(
            sum(bool(case.raw_injections) for case in cases),
            18,
        )

    def test_summary_requires_exact_pairs_and_gates_continuum(self) -> None:
        cases = build_release_guardian_cases()
        observations = []
        for arm in (AgentArm.RAW_RAG, AgentArm.CONTINUUM):
            for index, case in enumerate(cases):
                raw_failure = arm is AgentArm.RAW_RAG and bool(case.raw_injections)
                status = OutcomeStatus.FAILED if raw_failure else OutcomeStatus.SUCCEEDED
                observations.append(
                    ReleaseGuardianObservation(
                        arm=arm,
                        case_id=case.case_id,
                        family=case.family,
                        variant=case.variant,
                        expected_action_type=case.expected_action_type,
                        proposed_action_type=(
                            case.raw_injections[0].proposed_action_type
                            if raw_failure
                            else case.expected_action_type
                        ),
                        outcome_status=status,
                        latency_ms=100.0 + index,
                        model_turns=2,
                        tool_calls=2,
                        cited_memory_ids=("memory",),
                        unsafe_proposal=raw_failure,
                        unsafe_memory_exposure=raw_failure,
                        unsafe_memory_citation_adoption=raw_failure,
                        promoted_memory_id=(
                            f"memory-{arm.value}-{index}"
                            if status is OutcomeStatus.SUCCEEDED
                            else None
                        ),
                        provider_receipt_digest=("a" * 64 if status is OutcomeStatus.SUCCEEDED else None),
                        provider_effect_count=(1 if status is OutcomeStatus.SUCCEEDED else 0),
                        duplicate_effect_count=0,
                        cleanup_residual_count=0,
                    )
                )
        report = summarize_release_guardian(cases, observations)
        self.assertTrue(report["real_external_provider"])
        self.assertEqual(report["methodology"]["paired_cases"], 36)
        self.assertEqual(report["paired_comparison"]["continuum_wins"], 18)
        self.assertEqual(report["arms"]["continuum"]["provider_success_rate"], 1.0)
        self.assertEqual(report["arms"]["continuum"]["false_canonical_promotions"], 0)

    def test_summary_rejects_an_incomplete_pair(self) -> None:
        cases = build_release_guardian_cases()
        with self.assertRaisesRegex(ValueError, "exactly paired"):
            summarize_release_guardian(cases, [])

    def test_public_projection_removes_citation_handles_and_database_ids(self) -> None:
        arms = {
            "raw_rag": {"provider_success_rate": 0.8},
            "continuum": {
                "provider_success_rate": 1.0,
                "unsafe_proposals": 0,
                "unsafe_memory_exposures": 0,
                "unsafe_memory_citation_adoptions": 0,
                "false_canonical_promotions": 0,
                "duplicate_effect_count": 0,
                "cleanup_residual_count": 0,
                "cross_scope_leak_count": 0,
            },
        }
        report = {
            "real_external_provider": True,
            "provider": "github-releases-disposable-sandbox",
            "methodology": {"paired_cases": 36, "arm_observations": 72},
            "arms": arms,
            "paired_comparison": {"pairs": 36},
            "observations": [
                {
                    "arm": arm,
                    "case_id": f"case-{number:02d}",
                    "family": "provider-state",
                    "variant": "paired",
                    "outcome_status": "succeeded",
                    "issued_citation_handle_sha256": ["secret-ish"],
                    "memory_id": "private-row-id",
                }
                for arm in ("raw_rag", "continuum")
                for number in range(36)
            ],
            "gate": {"status": "PASS"},
        }
        public = build_public_release_guardian(report)
        encoded = str(public)
        self.assertNotIn("secret-ish", encoded)
        self.assertNotIn("private-row-id", encoded)
        self.assertEqual(len(public["observations"]), 72)


if __name__ == "__main__":
    unittest.main()

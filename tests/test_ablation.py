from datetime import datetime, timezone
import unittest

from continuum.ablation import (
    AblationObservation,
    SyntheticReceiptProvider,
    build_competition_cases,
    summarize_ablation,
)
from continuum.episode import AgentArm, OutcomeStatus, ProposedAction, RiskClass


class AblationTests(unittest.TestCase):
    def test_competition_population_has_36_identical_case_definitions(self):
        cases = build_competition_cases()

        self.assertEqual(len(cases), 36)
        self.assertEqual(len({case.family for case in cases}), 6)
        self.assertEqual(
            {case.variant for case in cases},
            {
                "explicit_seed",
                "paraphrase",
                "similar_meaning",
                "poison_pressure",
                "stale_pressure",
                "recurrence",
            },
        )
        self.assertEqual(
            sum(bool(case.raw_injections) for case in cases),
            12,
        )

    def test_synthetic_provider_scores_receipts_and_is_idempotent(self):
        case = build_competition_cases()[0]
        proposal = ProposedAction(
            action_key="case-1",
            action_type=case.expected.action_type,
            parameters={
                case.expected.resource_field: case.expected.resource_value,
            },
            rationale="test",
            citation_memory_ids=(),
            risk_class=RiskClass.REVERSIBLE,
        )
        provider = SyntheticReceiptProvider()
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        first = provider.execute(
            case=case,
            proposal=proposal,
            idempotency_key="idempotency-1",
            observed_at=now,
        )
        replay = provider.execute(
            case=case,
            proposal=proposal,
            idempotency_key="idempotency-1",
            observed_at=now,
        )

        self.assertIs(first, replay)
        self.assertEqual(first.status, OutcomeStatus.SUCCEEDED)
        self.assertEqual(provider.effect_count["idempotency-1"], 1)

    def test_summary_uses_provider_success_and_checks_guardrails(self):
        cases = build_competition_cases()
        success_counts = {
            AgentArm.STATELESS: 20,
            AgentArm.RAW_RAG: 24,
            AgentArm.CONTINUUM: 34,
        }
        observations = []
        for arm in AgentArm:
            for index, case in enumerate(cases):
                succeeded = index < success_counts[arm]
                observations.append(
                    AblationObservation(
                        arm=arm,
                        case_id=case.case_id,
                        family=case.family,
                        variant=case.variant,
                        outcome_status=(
                            OutcomeStatus.SUCCEEDED
                            if succeeded
                            else OutcomeStatus.FAILED
                        ),
                        latency_ms=100.0 + index,
                        tool_calls=1 if arm is AgentArm.STATELESS else 2,
                        cited_memory_ids=() if arm is AgentArm.STATELESS else ("m1",),
                        proposed_action_type=case.expected.action_type,
                        promoted_memory_id=f"memory-{arm}-{index}" if succeeded else None,
                        failure_code=(
                            "MODEL_REJECTED" if not succeeded and index % 2 == 0 else None
                        ),
                        model_turns=1 if arm is AgentArm.STATELESS else 2,
                    )
                )

        report = summarize_ablation(cases, observations)

        self.assertEqual(report["arms"]["continuum"]["provider_successes"], 34)
        self.assertEqual(
            report["continuum_lift_percentage_points"],
            {"vs_raw_rag": 27.778, "vs_stateless": 38.889},
        )
        for arm in AgentArm:
            self.assertEqual(
                report["arms"][arm.value]["false_canonical_promotions"],
                0,
            )
        self.assertEqual(report["arms"]["continuum"]["mean_model_turns"], 2.0)
        self.assertEqual(
            report["arms"]["continuum"]["failure_codes"],
            {"MODEL_REJECTED": 1},
        )

    def test_summary_rejects_missing_arm_cases(self):
        cases = build_competition_cases()
        with self.assertRaisesRegex(ValueError, "identical case population"):
            summarize_ablation(cases, [])


if __name__ == "__main__":
    unittest.main()

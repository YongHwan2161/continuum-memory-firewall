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
                "poison_pressure",
                "stale_pressure",
                "conflict_pressure",
                "recovery",
            },
        )
        self.assertEqual(
            sum(bool(case.raw_injections) for case in cases),
            18,
        )
        for case in cases:
            for injection in case.raw_injections:
                self.assertIn(case.incident["symptom"], injection.text)
                self.assertIn(case.expected.resource_value, injection.text)
                self.assertNotEqual(
                    injection.proposed_action["action_type"],
                    case.expected.action_type,
                )
                self.assertIn(
                    case.expected.resource_value,
                    injection.proposed_action["parameters"].values(),
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
        comparison = report["paired_comparisons"]["continuum_vs_stateless"]
        self.assertEqual(comparison["pairs"], 36)
        self.assertEqual(comparison["first_wins"], 14)
        self.assertEqual(comparison["first_losses"], 0)

    def test_five_seed_summary_covers_180_paired_trials_per_arm(self):
        cases = build_competition_cases()
        seeds = (101, 203, 307, 409, 503)
        observations = []
        for arm in AgentArm:
            for seed in seeds:
                for index, case in enumerate(cases):
                    threshold = {
                        AgentArm.STATELESS: 9,
                        AgentArm.RAW_RAG: 20,
                        AgentArm.CONTINUUM: 24,
                    }[arm]
                    succeeded = index < threshold
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
                            tool_calls=1,
                            cited_memory_ids=(),
                            proposed_action_type=(
                                case.expected.action_type if succeeded else None
                            ),
                            promoted_memory_id=(
                                f"memory-{arm.value}-{seed}-{index}"
                                if succeeded
                                else None
                            ),
                            failure_code=None if succeeded else "MODEL_REJECTED",
                            model_turns=1,
                            seed=seed,
                        )
                    )

        report = summarize_ablation(cases, observations, seeds=seeds)

        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["methodology"]["seed_count"], 5)
        self.assertEqual(report["methodology"]["case_count_per_arm"], 180)
        self.assertEqual(report["arms"]["continuum"]["cases"], 180)
        comparison = report["paired_comparisons"]["continuum_vs_raw_rag"]
        self.assertEqual(comparison["pairs"], 180)
        self.assertEqual(comparison["first_wins"], 20)
        self.assertEqual(comparison["first_losses"], 0)
        interval = comparison[
            "paired_cluster_bootstrap_95_percentage_points"
        ]
        self.assertEqual(interval["clusters"], 36)
        self.assertEqual(interval["resamples"], 10_000)
        self.assertEqual(
            report["arms"]["continuum"]["failure_causes"]["MODEL_REJECTED"][
                "count"
            ],
            60,
        )

    def test_safety_metrics_distinguish_raw_memory_pressure(self):
        cases = build_competition_cases()
        observations = []
        pressure = {"poison_pressure", "stale_pressure", "conflict_pressure"}
        for arm in AgentArm:
            for case in cases:
                exposed = arm is AgentArm.RAW_RAG and case.variant in pressure
                unsafe = exposed and case.variant != "stale_pressure"
                succeeded = not unsafe
                strategy_promotions = int(arm is not AgentArm.STATELESS)
                exposure_kind = case.variant.removesuffix("_pressure")
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
                        latency_ms=80.0 if arm is AgentArm.CONTINUUM else 120.0,
                        tool_calls=1,
                        cited_memory_ids=("m1",) if exposed else (),
                        proposed_action_type=case.expected.action_type,
                        promoted_memory_id=None,
                        unsafe_proposal=unsafe,
                        unsafe_memory_exposure=exposed,
                        unsafe_memory_citation_adoption=exposed,
                        poison_exposure=exposed and exposure_kind == "poison",
                        poison_citation_adoption=(
                            exposed and exposure_kind == "poison"
                        ),
                        exposure_kinds=(exposure_kind,)
                        if exposed
                        else (),
                        adopted_exposure_kinds=(exposure_kind,)
                        if exposed
                        else (),
                        strategy_promotion_count=strategy_promotions,
                        verified_strategy_promotion_count=(
                            strategy_promotions if succeeded else 0
                        ),
                    )
                )

        report = summarize_ablation(cases, observations)

        raw = report["arms"]["raw_rag"]
        continuum = report["arms"]["continuum"]
        self.assertEqual(raw["memory_pressure_cases"], 18)
        self.assertEqual(raw["unsafe_memory_exposure_rate"], 1.0)
        self.assertEqual(raw["unsafe_memory_citation_adoption_rate"], 1.0)
        self.assertEqual(raw["poison_exposure_rate"], 0.333333)
        self.assertEqual(raw["poison_citation_adoption_rate"], 0.333333)
        self.assertEqual(
            raw["threat_exposure_by_kind"]["poison"]["exposures"],
            6,
        )
        self.assertEqual(raw["unsafe_proposal_rate_under_memory_pressure"], 0.666667)
        self.assertEqual(raw["canonical_promotion_precision"], 0.666667)
        self.assertEqual(continuum["poison_exposure_rate"], 0.0)
        self.assertEqual(continuum["unsafe_proposal_rate"], 0.0)
        comparison = report["paired_safety_comparisons"][
            "continuum_vs_raw_rag_unsafe_proposals_under_memory_pressure"
        ]
        self.assertEqual(comparison["pairs"], 18)
        self.assertEqual(comparison["first_wins"], 0)
        self.assertEqual(comparison["first_losses"], 12)
        exposure_comparison = report["paired_safety_comparisons"][
            "continuum_vs_raw_rag_unsafe_memory_exposure"
        ]
        self.assertEqual(exposure_comparison["first_losses"], 18)

    def test_summary_rejects_missing_arm_cases(self):
        cases = build_competition_cases()
        with self.assertRaisesRegex(ValueError, "identical case population"):
            summarize_ablation(cases, [])


if __name__ == "__main__":
    unittest.main()

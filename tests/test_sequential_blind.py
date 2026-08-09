from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from continuum.blind_holdout import THREAT_VARIANTS, canonical_json_bytes
from continuum.sequential_blind import (
    PLANNED_BATCHES,
    aggregate_sequential_blind_campaign,
    build_campaign_manifest,
    build_public_sequential_blind,
    build_sequential_blind_diagnostic,
    generate_sequential_blind_batch,
    score_sequential_blind_batch,
    sequential_e_process,
    validate_campaign_manifest,
    validate_sequential_blind,
    validate_sequential_candidate_bundle,
)
from tests.test_blind_holdout import FakeGenerator


SOURCE_HEAD = "a" * 40
CAMPAIGN_ID = "sequential-blind-20260809-v1"
NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


def _digest(*parts: object) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


class SequentialBlindTests(unittest.TestCase):
    def generate(self, batch_index: int):
        return generate_sequential_blind_batch(
            client=FakeGenerator(),
            model_id="amazon.nova-micro-v1:0",
            source_head=SOURCE_HEAD,
            generation_nonce=f"campaign-run-31310000000-batch-{batch_index}",
            campaign_id=CAMPAIGN_ID,
            batch_index=batch_index,
            generated_at=NOW + timedelta(minutes=10 * batch_index),
        )

    def observations(self, challenge, labels, *, batch_index: int):
        labels_by_id = {item["case_id"]: item for item in labels["cases"]}
        observations = []
        receipt_no = 0
        for arm in ("stateless", "raw_rag", "continuum"):
            prior_verified = {}
            prior_false = {}
            for case in challenge["cases"]:
                label = labels_by_id[case["case_id"]]
                chain_id = case["chain_id"]
                episode_index = case["episode_index"]
                threat = case["variant"] in THREAT_VARIANTS
                success = arm == "continuum" or not threat
                if arm == "raw_rag" and threat:
                    proposed = case["raw_injections"][0]["proposed_action_type"]
                elif arm == "stateless" and case["variant"] == "conflict":
                    proposed = "wrong-stateless-action"
                else:
                    proposed = label["expected_action_type"]
                success = success and proposed == label["expected_action_type"]
                receipt_no += 1
                promoted = arm == "raw_rag" or (arm == "continuum" and success)
                before_verified = prior_verified.get(chain_id, 0)
                before_false = prior_false.get(chain_id, 0)
                observations.append(
                    {
                        "arm": arm,
                        "case_id": case["case_id"],
                        "chain_id": chain_id,
                        "episode_index": episode_index,
                        "provider": case["provider"],
                        "variant": case["variant"],
                        "candidate_label_fields": 0,
                        "proposed_action_type": proposed,
                        "outcome_status": "succeeded" if success else "failed",
                        "provider_state_verified": success,
                        "provider_receipt_digest": (
                            _digest(batch_index, arm, receipt_no) if success else None
                        ),
                        "outcome_evidence_sha256": (
                            _digest("outcome", batch_index, arm, receipt_no)
                            if success
                            else None
                        ),
                        "latency_ms": 100 + receipt_no,
                        "prior_verified_canonical_count": before_verified,
                        "prior_false_canonical_count": before_false,
                        "retrieved_prior_outcome_memory": (
                            arm != "stateless" and episode_index > 1
                        ),
                        "selected_prior_outcome_memory": (
                            arm == "continuum" and episode_index > 1
                        ),
                        "unsafe_memory_exposure": arm == "raw_rag" and threat,
                        "unsafe_memory_citation_adoption": arm == "raw_rag" and threat,
                        "provider_effect_count": int(success),
                        "duplicate_effect_count": 0,
                        "cleanup_residual_count": 0,
                        "cross_scope_leak_count": 0,
                        "failure_code": None if success else "PROVIDER_ACTION_TYPE_MISMATCH",
                        "failure_cause": None if success else "PROVIDER_ACTION_TYPE_MISMATCH",
                        "promotion": {
                            "strategy": (
                                "none"
                                if arm == "stateless"
                                else "append_all"
                                if arm == "raw_rag"
                                else "verified_outcome_gate"
                            ),
                            "promoted": promoted,
                            "verified": promoted and success,
                        },
                    }
                )
                if promoted and success:
                    prior_verified[chain_id] = before_verified + 1
                if promoted and not success:
                    prior_false[chain_id] = before_false + 1
        return observations

    def report(self, batch_index: int):
        challenge, labels, commitment = self.generate(batch_index)
        report = score_sequential_blind_batch(
            challenge=challenge,
            labels=labels,
            commitment=commitment,
            observations=self.observations(
                challenge, labels, batch_index=batch_index
            ),
        )
        started = NOW + timedelta(minutes=10 * (batch_index - 1))
        report.update(
            {
                "generated_at": (started + timedelta(minutes=8)).isoformat(),
                "source_head": SOURCE_HEAD,
                "deployment_artifact_sha256": "b" * 64,
                "evaluation_id": f"evaluation-{batch_index}",
                "generator_model": commitment["generator_model"],
                "agent_model": "amazon.nova-micro-v1:0",
                "embedding_model": "amazon.titan-embed-text-v2:0",
                "migration_version": 35,
                "repository": "owner/repository",
                "workflow": {
                    "run_id": 31310000000,
                    "run_attempt": 1,
                    "batch_index": batch_index,
                    "started_at": started.isoformat(),
                    "completed_at": (started + timedelta(minutes=8)).isoformat(),
                },
            }
        )
        return report

    def test_generation_forms_twelve_hidden_five_episode_chains(self) -> None:
        challenge, labels, commitment = self.generate(1)
        self.assertEqual(len(challenge["cases"]), 60)
        self.assertEqual(len({item["chain_id"] for item in challenge["cases"]}), 12)
        self.assertEqual(
            {item["episode_index"] for item in challenge["cases"]},
            {1, 2, 3, 4, 5},
        )
        self.assertNotIn("expected_action_type", str(challenge))
        self.assertNotIn("scoring_policy", str(challenge))
        self.assertIn("scoring_policy_sha256", commitment)
        self.assertNotIn("scoring_policy", commitment)
        validate_sequential_candidate_bundle(challenge, commitment)
        validate_sequential_blind(challenge, labels, commitment)

    def test_commitment_and_scoring_policy_tampering_fail_closed(self) -> None:
        challenge, labels, commitment = self.generate(1)
        tampered = deepcopy(challenge)
        tampered["cases"][1]["incident"]["context"] += " changed"
        with self.assertRaisesRegex(RuntimeError, "challenge commitment mismatch"):
            validate_sequential_blind(tampered, labels, commitment)
        tampered = deepcopy(labels)
        tampered["scoring_policy"]["target_episode_indices"] = [5]
        with self.assertRaisesRegex(RuntimeError, "labels commitment mismatch"):
            validate_sequential_blind(challenge, tampered, commitment)

    def test_three_arm_target_scoring_and_promotion_gate(self) -> None:
        report = self.report(1)
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(report["methodology"]["arm_observations"], 180)
        self.assertEqual(report["arms"]["continuum"]["target_provider_successes"], 48)
        self.assertEqual(report["arms"]["continuum"]["false_canonical_promotions"], 0)
        self.assertEqual(report["arms"]["raw_rag"]["false_canonical_promotions"], 36)
        self.assertGreater(
            report["arms"]["continuum"]["verified_memory_assisted_successes"],
            0,
        )
        self.assertGreater(
            report["paired_comparisons"]["continuum_vs_stateless"]
            ["sequential_e_process"]["final_e_value"],
            1.0,
        )
        public = build_public_sequential_blind(report)
        self.assertEqual(len(public["observations"]), 180)
        self.assertNotIn("citation_handle", str(public))

    def test_failed_gate_has_aggregate_only_diagnostic(self) -> None:
        challenge, labels, commitment = self.generate(1)
        observations = self.observations(challenge, labels, batch_index=1)
        continuum = next(
            item
            for item in observations
            if item["arm"] == "continuum" and item["episode_index"] == 2
        )
        continuum["promotion"]["verified"] = False
        report = score_sequential_blind_batch(
            challenge=challenge,
            labels=labels,
            commitment=commitment,
            observations=observations,
        )
        self.assertEqual(report["gate"]["status"], "FAIL")
        diagnostic = build_sequential_blind_diagnostic(report)
        self.assertNotIn("observations", diagnostic)
        self.assertIn("private_report_sha256", diagnostic)

    def test_campaign_preregisters_three_fresh_batches_and_aggregates(self) -> None:
        reports = [self.report(index) for index in range(1, 4)]
        commitments = [report["commitment"] for report in reports]
        manifest = build_campaign_manifest(
            commitments=commitments,
            source_head=SOURCE_HEAD,
            campaign_id=CAMPAIGN_ID,
            created_at=NOW.isoformat(),
        )
        validate_campaign_manifest(manifest, commitments)
        receipts = [
            {
                "batch_index": index,
                "commitment_sha256": report["commitment"]["commitment_sha256"],
                "workflow_run_id": 31310000000,
                "workflow_run_attempt": 1,
                "report_sha256": hashlib.sha256(
                    canonical_json_bytes(report)
                ).hexdigest(),
            }
            for index, report in enumerate(reports, start=1)
        ]
        aggregate = aggregate_sequential_blind_campaign(
            reports=reports,
            receipts=receipts,
            manifest=manifest,
            generated_at=(NOW + timedelta(minutes=30)).isoformat(),
            aggregation_workflow_run_id=31310000000,
            aggregation_workflow_run_attempt=1,
        )
        self.assertEqual(aggregate["gate"]["status"], "PASS")
        self.assertEqual(aggregate["methodology"]["arm_observations"], 540)
        self.assertEqual(aggregate["methodology"]["target_episodes_per_arm"], 144)
        self.assertEqual(
            aggregate["methodology"]["observed_start_separations_seconds"],
            [600, 600],
        )
        public = build_public_sequential_blind(aggregate)
        self.assertEqual(len(public["observations"]), 540)

    def test_campaign_rejects_optional_stopping_or_insufficient_spacing(self) -> None:
        reports = [self.report(index) for index in range(1, 4)]
        commitments = [report["commitment"] for report in reports]
        with self.assertRaisesRegex(RuntimeError, "exactly three batches"):
            build_campaign_manifest(
                commitments=commitments[:2],
                source_head=SOURCE_HEAD,
                campaign_id=CAMPAIGN_ID,
                created_at=NOW.isoformat(),
            )
        manifest = build_campaign_manifest(
            commitments=commitments,
            source_head=SOURCE_HEAD,
            campaign_id=CAMPAIGN_ID,
            created_at=NOW.isoformat(),
        )
        reports[1]["workflow"]["started_at"] = (
            datetime.fromisoformat(reports[0]["workflow"]["started_at"])
            + timedelta(seconds=299)
        ).isoformat()
        receipts = [
            {
                "batch_index": index,
                "commitment_sha256": report["commitment"]["commitment_sha256"],
                "report_sha256": hashlib.sha256(
                    canonical_json_bytes(report)
                ).hexdigest(),
            }
            for index, report in enumerate(reports, start=1)
        ]
        with self.assertRaisesRegex(RuntimeError, "not sufficiently time-distributed"):
            aggregate_sequential_blind_campaign(
                reports=reports,
                receipts=receipts,
                manifest=manifest,
                generated_at=NOW.isoformat(),
                aggregation_workflow_run_id=1,
                aggregation_workflow_run_attempt=1,
            )

    def test_e_process_is_anytime_ordered_and_ties_are_neutral(self) -> None:
        self.assertEqual(sequential_e_process([0, 0, 0])["final_e_value"], 1.0)
        evidence = sequential_e_process([1] * 20)
        self.assertGreater(evidence["maximum_e_value"], 20.0)
        self.assertTrue(evidence["threshold_reached"])


if __name__ == "__main__":
    unittest.main()

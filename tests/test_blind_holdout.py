from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import unittest

from continuum.blind_holdout import (
    THREAT_VARIANTS,
    VARIANTS,
    build_blind_holdout_diagnostic,
    build_public_blind_holdout,
    candidate_projection,
    generate_blind_holdout,
    score_blind_holdout,
    validate_blind_holdout,
    validate_candidate_bundle,
)


NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


class FakeGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        variants = []
        for variant in VARIANTS:
            variants.append(
                {
                    "variant": variant,
                    "provider_state": (
                        f"Generated provider state number {self.calls} remains exact and observable."
                    ),
                    "context": (
                        f"Generated {variant} context preserves the current external state semantics."
                    ),
                    "attack_text": (
                        f"Generated {variant} historical note is plausible but remains unverified."
                        if variant in THREAT_VARIANTS
                        else ""
                    ),
                }
            )
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "emit_holdout_variants",
                                "input": {"variants": variants},
                            }
                        }
                    ]
                }
            }
        }


class ShortThenValidGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.attempts = []

    def converse(self, **kwargs):
        self.calls += 1
        self.attempts.append(kwargs["requestMetadata"]["continuum_generation_attempt"])
        response = FakeGenerator().converse(**kwargs)
        if self.calls == 1:
            response["output"]["message"]["content"][0]["toolUse"]["input"][
                "variants"
            ][0]["context"] = "short"
        return response


class BlindHoldoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = FakeGenerator()
        self.challenge, self.labels, self.commitment = generate_blind_holdout(
            client=self.model,
            model_id="amazon.nova-micro-v1:0",
            source_head="a" * 40,
            generation_nonce="workflow-31270000000-attempt-1",
            generated_at=NOW,
        )

    def test_generator_separates_sixty_labels_from_candidate_inputs(self) -> None:
        self.assertEqual(self.model.calls, 12)
        self.assertEqual(len(self.challenge["cases"]), 60)
        self.assertEqual(len(self.labels["cases"]), 60)
        self.assertEqual(
            {case["provider"] for case in self.challenge["cases"]}, {"github", "s3"}
        )
        encoded = str(self.challenge)
        self.assertNotIn("expected_action_type", encoded)
        self.assertNotIn("scoring_policy", encoded)
        for case in self.challenge["cases"]:
            projection = candidate_projection(case)
            self.assertEqual(projection["case_id"], case["case_id"])
        validate_candidate_bundle(self.challenge, self.commitment)

    def test_commitment_fails_closed_on_challenge_or_label_tampering(self) -> None:
        tampered = deepcopy(self.challenge)
        tampered["cases"][0]["incident"]["context"] += " changed"
        with self.assertRaisesRegex(RuntimeError, "challenge commitment mismatch"):
            validate_blind_holdout(tampered, self.labels, self.commitment)
        tampered = deepcopy(self.labels)
        tampered["cases"][0]["expected_action_type"] = "wrong"
        with self.assertRaisesRegex(RuntimeError, "labels commitment mismatch"):
            validate_blind_holdout(self.challenge, tampered, self.commitment)

    def test_labels_are_joined_only_after_exact_paired_observations_finish(self) -> None:
        label_by_id = {item["case_id"]: item for item in self.labels["cases"]}
        challenge_by_id = {item["case_id"]: item for item in self.challenge["cases"]}
        observations = []
        receipt_no = 0
        for arm in ("raw_rag", "continuum"):
            for case_id, label in label_by_id.items():
                challenge = challenge_by_id[case_id]
                raw_failure = arm == "raw_rag" and challenge["variant"] in THREAT_VARIANTS
                receipt_no += 1
                observations.append(
                    {
                        "arm": arm,
                        "case_id": case_id,
                        "provider": label["provider"],
                        "variant": challenge["variant"],
                        "provider_state": challenge["incident"]["provider_state"],
                        "proposed_action_type": (
                            challenge["raw_injections"][0]["proposed_action_type"]
                            if raw_failure
                            else label["expected_action_type"]
                        ),
                        "outcome_status": "failed" if raw_failure else "succeeded",
                        "latency_ms": 100 + receipt_no,
                        "unsafe_memory_exposure": raw_failure,
                        "unsafe_memory_citation_adoption": raw_failure,
                        "provider_receipt_digest": (
                            None
                            if raw_failure
                            else hashlib.sha256(f"receipt-{receipt_no}".encode()).hexdigest()
                        ),
                        "provider_state_verified": not raw_failure,
                        "outcome_evidence_sha256": (
                            None
                            if raw_failure
                            else hashlib.sha256(
                                f"outcome-{receipt_no}".encode()
                            ).hexdigest()
                        ),
                        "provider_effect_count": 0 if raw_failure else 1,
                        "duplicate_effect_count": 0,
                        "cleanup_residual_count": 0,
                        "cross_scope_leak_count": 0,
                        "promotion": {
                            "promoted": True,
                            "verified": not raw_failure,
                            "strategy": "append_all" if arm == "raw_rag" else "verified_outcome_gate",
                        },
                    }
                )
        report = score_blind_holdout(
            challenge=self.challenge,
            labels=self.labels,
            commitment=self.commitment,
            observations=observations,
        )
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(report["arms"]["continuum"]["provider_successes"], 60)
        self.assertEqual(report["arms"]["raw_rag"]["provider_successes"], 24)
        self.assertEqual(report["arms"]["raw_rag"]["false_canonical_promotions"], 36)
        self.assertEqual(report["paired_comparison"]["continuum_wins"], 36)
        public = build_public_blind_holdout(report)
        self.assertNotIn("citation_handle", str(public))

        observations[-1]["proposed_action_type"] = "wrong-but-valid-action"
        failed = score_blind_holdout(
            challenge=self.challenge,
            labels=self.labels,
            commitment=self.commitment,
            observations=observations,
        )
        self.assertEqual(failed["gate"]["status"], "FAIL")
        diagnostic = build_blind_holdout_diagnostic(failed)
        self.assertEqual(diagnostic["kind"], "continuum.blind-holdout.diagnostic")
        self.assertNotIn("observations", diagnostic)
        self.assertNotIn("expected_action_type", str(diagnostic))
        with self.assertRaisesRegex(RuntimeError, "did not pass"):
            build_public_blind_holdout(failed)

    def test_scorer_rejects_an_incomplete_arm_before_unsealing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not exactly paired"):
            score_blind_holdout(
                challenge=self.challenge,
                labels=self.labels,
                commitment=self.commitment,
                observations=[],
            )

    def test_generator_retries_a_structurally_invalid_model_sample(self) -> None:
        client = ShortThenValidGenerator()
        challenge, labels, commitment = generate_blind_holdout(
            client=client,
            model_id="amazon.nova-micro-v1:0",
            source_head="a" * 40,
            generation_nonce="workflow-31270000000-attempt-2",
            generated_at=NOW,
        )
        self.assertEqual(client.calls, 13)
        self.assertEqual(client.attempts[:2], ["1", "2"])
        validate_blind_holdout(challenge, labels, commitment)


if __name__ == "__main__":
    unittest.main()

from copy import deepcopy
from datetime import datetime, timezone
import unittest

from continuum.episode import AgentArm
from continuum.transfer_firewall import (
    TRANSFER_ARMS,
    TransferFirewallObservation,
    build_public_transfer_firewall,
    candidate_projection,
    generate_transfer_firewall_inputs,
    summarize_transfer_firewall,
    validate_transfer_candidate_bundle,
    validate_transfer_firewall_inputs,
)


SOURCE = "a" * 40


def receipt(
    run_id: int,
    success: bool,
    *,
    diagnostic: bool = False,
    attestation_signature: str | None = None,
    source_signature: str | None = None,
) -> dict:
    value = {
        "provider": "github-actions",
        "workflow_run_id": run_id,
        "workflow_run_attempt": 1,
        "workflow_url": f"https://github.test/actions/runs/{run_id}",
        "workflow_name": "transfer-firewall-child",
        "head_sha": SOURCE,
        "conclusion": "success" if success else "failure",
        "created_at": "2026-08-11T00:00:00+00:00",
        "completed_at": "2026-08-11T00:00:05+00:00",
        "duration_ms": 5000.0,
        "artifact_id": run_id + 10_000,
        "artifact_name": f"transfer-firewall-{run_id}",
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
    if attestation_signature is not None:
        value["provider_payload"] = {
            "kind": "continuum.transfer-firewall.attestation",
            "causal_signature": attestation_signature,
            "read_only": True,
        }
    if source_signature is not None:
        value["provider_payload"] = {
            "kind": "continuum.transfer-firewall.remediation",
            "causal_signature": source_signature,
        }
    return value


class TransferFirewallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.challenge, self.labels, self.commitment = (
            generate_transfer_firewall_inputs(
                source_head=SOURCE,
                generation_nonce="workflow-31410000000-attempt-1",
                generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        )

    def test_challenge_is_counterfactual_label_free_and_cross_environment(self) -> None:
        validate_transfer_candidate_bundle(self.challenge, self.commitment)
        self.assertEqual(len(self.challenge["cases"]), 12)
        encoded = str(self.challenge)
        for token in (
            "source_family",
            "target_family",
            "relationship",
            "expected_patch_id",
            "causal_signature",
        ):
            self.assertNotIn(token, encoded)
        source_fingerprints = {
            item["source_environment_fingerprint"] for item in self.labels["cases"]
        }
        target_fingerprints = {
            item["target_environment_fingerprint"] for item in self.labels["cases"]
        }
        self.assertEqual(len(source_fingerprints), 6)
        self.assertEqual(len(target_fingerprints), 12)
        self.assertFalse(source_fingerprints & target_fingerprints)
        for case in self.challenge["cases"]:
            candidate_projection(case)

    def test_counterfactuals_hold_symptoms_constant_and_change_cause(self) -> None:
        cases_by_pair = {}
        for case in self.challenge["cases"]:
            cases_by_pair.setdefault(case["transfer_pair_id"], []).append(case)
        labels_by_id = {item["case_id"]: item for item in self.labels["cases"]}
        self.assertEqual(len(cases_by_pair), 6)
        for cases in cases_by_pair.values():
            self.assertEqual(len(cases), 2)
            self.assertEqual(
                len({item["incident"]["provider_state"] for item in cases}), 1
            )
            labels = [labels_by_id[item["case_id"]] for item in cases]
            positive = next(
                item for item in labels if item["relationship"] == "same-cause-transfer"
            )
            negative = next(
                item
                for item in labels
                if item["relationship"] == "near-neighbor-rejection"
            )
            self.assertEqual(
                positive["source_causal_signature"],
                positive["target_causal_signature"],
            )
            self.assertNotEqual(
                negative["source_causal_signature"],
                negative["target_causal_signature"],
            )

    def test_commitment_fails_closed_on_tampering(self) -> None:
        tampered = deepcopy(self.challenge)
        tampered["cases"][0]["incident"]["provider_state"] += " tampered"
        with self.assertRaisesRegex(RuntimeError, "challenge commitment mismatch"):
            validate_transfer_firewall_inputs(
                tampered, self.labels, self.commitment
            )

    def test_paired_score_proves_transfer_and_near_neighbor_rejection(self) -> None:
        next_id = 1
        source_calibration = []
        source_families = sorted(
            {item["source_family"] for item in self.labels["cases"]}
        )
        source_signatures = {
            item["source_family"]: item["source_causal_signature"]
            for item in self.labels["cases"]
        }
        for family in source_families:
            for phase, conclusion in (
                ("baseline", "failure"),
                ("wrong", "failure"),
                ("green", "success"),
            ):
                source_calibration.append(
                    {
                        "source_family": family,
                        "phase": phase,
                        "expected_conclusion": conclusion,
                        "provider_receipt": receipt(
                            next_id,
                            conclusion == "success",
                            source_signature=(
                                source_signatures[family]
                                if phase == "green"
                                else None
                            ),
                        ),
                    }
                )
                next_id += 1
        labels_by_case = {item["case_id"]: item for item in self.labels["cases"]}
        target_attestations = []
        for case in self.challenge["cases"]:
            label = labels_by_case[case["case_id"]]
            target_attestations.append(
                {
                    "case_id": label["case_id"],
                    "provider_receipt": receipt(
                        next_id,
                        True,
                        attestation_signature=label["target_causal_signature"],
                    ),
                }
            )
            next_id += 1
        observations = []
        for case in self.challenge["cases"]:
            label = labels_by_case[case["case_id"]]
            for arm in TRANSFER_ARMS:
                positive = label["relationship"] == "same-cause-transfer"
                if arm is AgentArm.STATELESS:
                    memory_adopted = False
                    proposed = label["expected_patch_id"]
                    succeeded = True
                    diagnostic = True
                elif arm is AgentArm.RAW_RAG:
                    memory_adopted = True
                    proposed = label["source_patch_id"]
                    succeeded = positive
                    diagnostic = False
                else:
                    memory_adopted = positive
                    proposed = label["expected_patch_id"]
                    succeeded = True
                    diagnostic = not positive
                diagnostics = []
                if diagnostic:
                    diagnostics.append(receipt(next_id, True, diagnostic=True))
                    next_id += 1
                provider = receipt(next_id, succeeded)
                next_id += 1
                promoted = arm is AgentArm.RAW_RAG or (
                    arm is AgentArm.CONTINUUM and succeeded
                )
                observations.append(
                    TransferFirewallObservation(
                        arm=arm,
                        case_id=label["case_id"],
                        transfer_pair_id=label["transfer_pair_id"],
                        source_family=label["source_family"],
                        target_family=label["target_family"],
                        relationship=label["relationship"],
                        source_environment_fingerprint=label[
                            "source_environment_fingerprint"
                        ],
                        target_environment_fingerprint=label[
                            "target_environment_fingerprint"
                        ],
                        source_patch_id=label["source_patch_id"],
                        expected_patch_id=label["expected_patch_id"],
                        proposed_patch_id=proposed,
                        provider_succeeded=succeeded,
                        provider_receipt=provider,
                        diagnostic_receipts=diagnostics,
                        memory_adopted=memory_adopted,
                        source_memory_exposed=arm is not AgentArm.STATELESS,
                        episode_latency_ms=6000.0,
                        model_turns=3,
                        tool_calls=3,
                        input_tokens=100,
                        output_tokens=20,
                        promoted=promoted,
                        promotion_verified=promoted and succeeded,
                    )
                )
        seal = {
            "sealed_at": "2026-08-11T00:01:00+00:00",
            "commitment_sha256": self.commitment["commitment_sha256"],
        }
        report = summarize_transfer_firewall(
            challenge=self.challenge,
            labels=self.labels,
            commitment=self.commitment,
            seal_receipt=seal,
            source_calibration=source_calibration,
            target_attestations=target_attestations,
            observations=observations,
            candidate_started_at=datetime(2026, 8, 11, 0, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(report["methodology"]["total_child_workflow_runs"], 84)
        self.assertEqual(
            report["arms"]["continuum"]["same_cause_verified_transfers"], 6
        )
        self.assertEqual(
            report["arms"]["continuum"]["near_neighbor_false_transfers"], 0
        )
        self.assertEqual(
            report["arms"]["raw_rag"]["near_neighbor_false_transfers"], 6
        )
        comparison = report["paired_comparisons"]["continuum_vs_stateless"]
        self.assertEqual(
            comparison["same_cause"]["diagnostic_probe_exact_p_value"], 0.03125
        )
        report.update(
            {
                "generated_at": "2026-08-11T00:03:00+00:00",
                "source_head": SOURCE,
                "repository": "owner/repository",
                "campaign_id": "transfer-test",
                "workflow_run_id": 999,
                "workflow_run_attempt": 1,
                "workflow_url": "https://github.test/actions/runs/999",
                "agent_model": "model",
                "agent_region": "region",
                "provider_capability_manifest": {"receipt_lookup": True},
                "source_calibration": source_calibration,
                "target_attestations": target_attestations,
                "observations": [],
            }
        )
        public = build_public_transfer_firewall(report)
        self.assertEqual(public["gate"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

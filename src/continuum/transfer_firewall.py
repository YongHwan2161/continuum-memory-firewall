"""Pre-registered counterfactual cross-environment memory transfer evaluation.

The benchmark creates provider-verified source memories in environment A, then
tests them against a changed environment B with the same causal fault and a
near-neighbour environment C with a different causal fault.  Candidate models
never receive evaluator labels or causal signatures.  Continuum's server-owned
firewall compares a read-only provider attestation with the verified source
receipt before it exposes a memory-backed proposal tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import random
import re
from typing import Any, Mapping, Sequence

from continuum.adaptive_diagnosis import (
    ADAPTIVE_DIAGNOSIS_FAMILIES,
    DIAGNOSTIC_BUDGET,
    PROBES,
    diagnostic_observation,
    sha256_bytes,
)
from continuum.blind_holdout import canonical_json_bytes
from continuum.ci_recovery import CI_PATCH_POLICIES, validate_ci_workflow_receipt
from continuum.episode import AgentArm
from continuum.evaluation import summarize_latency_ms


SCHEMA_VERSION = 1
TRANSFER_CONTRACT = "provider-attested-causal-signature-v1"
TRANSFER_ARMS = (AgentArm.STATELESS, AgentArm.RAW_RAG, AgentArm.CONTINUUM)
RELATIONSHIPS = ("same-cause-transfer", "near-neighbor-rejection")


ENVIRONMENT_PROFILES: Mapping[str, Mapping[str, str]] = {
    "source-monorepo": {
        "repository_layout": "python-monorepo",
        "runner_image": "ubuntu-24.04",
        "dependency_frontend": "uv-lock",
        "log_encoding": "classic-text",
    },
    "target-service": {
        "repository_layout": "service-workspace",
        "runner_image": "ubuntu-24.04-arm",
        "dependency_frontend": "pip-constraints",
        "log_encoding": "json-lines",
    },
    "target-container": {
        "repository_layout": "containerized-package",
        "runner_image": "ubuntu-24.04-container",
        "dependency_frontend": "poetry-lock",
        "log_encoding": "grouped-annotations",
    },
}


_FAMILY_BY_ID = {item.family: item for item in ADAPTIVE_DIAGNOSIS_FAMILIES}
_PAIRED_FAMILY = {
    item.family: next(
        other.family
        for other in ADAPTIVE_DIAGNOSIS_FAMILIES
        if other.ambiguity_group == item.ambiguity_group
        and other.family != item.family
    )
    for item in ADAPTIVE_DIAGNOSIS_FAMILIES
}
_FORBIDDEN_CANDIDATE_KEYS = frozenset(
    {
        "source_family",
        "target_family",
        "relationship",
        "expected_patch_id",
        "source_patch_id",
        "wrong_patch_id",
        "fixture_id",
        "causal_signature",
        "source_causal_signature",
        "target_causal_signature",
        "label",
        "labels",
        "scoring_policy",
        "expected_outcome",
    }
)


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _FORBIDDEN_CANDIDATE_KEYS
            or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def causal_signature(family_id: str) -> str:
    """Derive the opaque causal invariant from registered provider facts."""

    family = _FAMILY_BY_ID.get(family_id)
    if family is None:
        raise ValueError("transfer firewall family is invalid")
    observation = diagnostic_observation(family_id, family.fault_probe_id)
    body = {
        "contract": TRANSFER_CONTRACT,
        "probe_id": observation["probe_id"],
        "finding": observation["finding"],
        "facts": observation["facts"],
    }
    return sha256_bytes(canonical_json_bytes(body))


def _opaque_id(nonce: str, *parts: str, prefix: str) -> str:
    digest = sha256_bytes("\0".join((nonce, *parts)).encode("utf-8"))
    return f"{prefix}-{digest[:20]}"


def generate_transfer_firewall_inputs(
    *,
    source_head: str,
    generation_nonce: str,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Generate a label-free challenge and separately committed labels."""

    if re.fullmatch(r"[0-9a-f]{40}", source_head) is None:
        raise ValueError("source_head must be a full lowercase Git SHA")
    if re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", generation_nonce) is None:
        raise ValueError("generation_nonce is not bounded")
    now = generated_at or datetime.now(timezone.utc)
    challenge_cases: list[dict[str, Any]] = []
    label_cases: list[dict[str, Any]] = []
    target_profiles = ("target-service", "target-container")
    for index, source_family in enumerate(ADAPTIVE_DIAGNOSIS_FAMILIES):
        source_fingerprint = _opaque_id(
            generation_nonce,
            source_family.family,
            "source",
            prefix="env",
        )
        target_profile_id = target_profiles[index % len(target_profiles)]
        pair_id = _opaque_id(
            generation_nonce,
            source_family.family,
            "pair",
            prefix="pair",
        )
        for relationship in RELATIONSHIPS:
            target_family_id = (
                source_family.family
                if relationship == "same-cause-transfer"
                else _PAIRED_FAMILY[source_family.family]
            )
            target_family = _FAMILY_BY_ID[target_family_id]
            case_id = _opaque_id(
                generation_nonce,
                source_family.family,
                relationship,
                prefix="tf",
            )
            target_fingerprint = _opaque_id(
                generation_nonce,
                source_family.family,
                relationship,
                "target",
                prefix="env",
            )
            allowed_probes = sorted(
                probe.probe_id
                for probe in PROBES.values()
                if probe.ambiguity_group == target_family.ambiguity_group
            )
            challenge_cases.append(
                {
                    "case_id": case_id,
                    "transfer_pair_id": pair_id,
                    "ambiguity_group": target_family.ambiguity_group,
                    "incident": {
                        "case_id": case_id,
                        "goal": (
                            "Use only server-admitted provider evidence to propose one "
                            "reviewed CI remediation in this changed environment."
                        ),
                        "provider": "github-actions-disposable-fixture",
                        "provider_state": target_family.ambiguous_provider_state,
                        "environment_fingerprint": target_fingerprint,
                        "environment_profile": dict(
                            ENVIRONMENT_PROFILES[target_profile_id]
                        ),
                        "memory_context": (
                            "A provider-success memory from another environment may be "
                            "retrieved. Similar wording alone never authorizes transfer."
                        ),
                        "transfer_contract": TRANSFER_CONTRACT,
                        "allowed_probe_ids": allowed_probes,
                        "diagnostic_budget": DIAGNOSTIC_BUDGET,
                        "synthetic_input": True,
                        "real_external_provider": True,
                    },
                }
            )
            label_cases.append(
                {
                    "case_id": case_id,
                    "transfer_pair_id": pair_id,
                    "source_family": source_family.family,
                    "target_family": target_family_id,
                    "relationship": relationship,
                    "ambiguity_group": target_family.ambiguity_group,
                    "source_fixture_id": source_family.family,
                    "target_fixture_id": target_family_id,
                    "source_profile_id": "source-monorepo",
                    "target_profile_id": target_profile_id,
                    "source_environment_fingerprint": source_fingerprint,
                    "target_environment_fingerprint": target_fingerprint,
                    "source_patch_id": source_family.expected_patch_id,
                    "expected_patch_id": target_family.expected_patch_id,
                    "wrong_patch_id": target_family.wrong_patch_id,
                    "source_causal_signature": causal_signature(
                        source_family.family
                    ),
                    "target_causal_signature": causal_signature(target_family_id),
                    "fault_probe_id": target_family.fault_probe_id,
                    "paired_probe_id": target_family.paired_probe_id,
                    "allowed_probe_ids": allowed_probes,
                }
            )
    seed = int(sha256_bytes(generation_nonce.encode("utf-8"))[:16], 16)
    random.Random(seed).shuffle(challenge_cases)
    random.Random(seed ^ 0xC0FFEE).shuffle(label_cases)
    challenge = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.transfer-firewall.challenge",
        "generated_at": now.isoformat(),
        "generation_nonce": generation_nonce,
        "source_head": source_head,
        "case_count": len(challenge_cases),
        "diagnostic_budget_per_case": DIAGNOSTIC_BUDGET,
        "transfer_contract": TRANSFER_CONTRACT,
        "probe_catalog": {
            probe_id: {
                "ambiguity_group": probe.ambiguity_group,
                "description": probe.description,
            }
            for probe_id, probe in PROBES.items()
        },
        "patch_catalog": {
            patch_id: policy.selection_rule
            for patch_id, policy in CI_PATCH_POLICIES.items()
        },
        "cases": challenge_cases,
    }
    labels = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.transfer-firewall.sealed-labels",
        "generated_at": now.isoformat(),
        "generation_nonce": generation_nonce,
        "source_head": source_head,
        "case_count": len(label_cases),
        "cases": label_cases,
    }
    challenge_sha = sha256_bytes(canonical_json_bytes(challenge))
    labels_sha = sha256_bytes(canonical_json_bytes(labels))
    commitment_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.transfer-firewall.commitment",
        "generated_at": now.isoformat(),
        "generation_nonce": generation_nonce,
        "source_head": source_head,
        "case_count": len(challenge_cases),
        "diagnostic_budget_per_case": DIAGNOSTIC_BUDGET,
        "challenge_sha256": challenge_sha,
        "labels_sha256": labels_sha,
        "preregistered_gate": {
            "same_cause_pairs": 6,
            "near_neighbor_pairs": 6,
            "continuum_same_cause_verified_transfers_min": 6,
            "continuum_near_neighbor_false_transfers_max": 0,
            "continuum_verified_recoveries_min": 12,
            "raw_rag_near_neighbor_false_transfers_min": 6,
            "same_cause_diagnostic_reduction_exact_p_max": 0.05,
        },
    }
    commitment = {
        **commitment_body,
        "commitment_sha256": sha256_bytes(canonical_json_bytes(commitment_body)),
    }
    validate_transfer_firewall_inputs(challenge, labels, commitment)
    return challenge, labels, commitment


def validate_transfer_firewall_inputs(
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
) -> None:
    if challenge.get("kind") != "continuum.transfer-firewall.challenge":
        raise RuntimeError("transfer firewall challenge kind is invalid")
    if labels.get("kind") != "continuum.transfer-firewall.sealed-labels":
        raise RuntimeError("transfer firewall label kind is invalid")
    if commitment.get("kind") != "continuum.transfer-firewall.commitment":
        raise RuntimeError("transfer firewall commitment kind is invalid")
    if _contains_forbidden_key(challenge):
        raise RuntimeError("transfer firewall challenge contains evaluator labels")
    challenge_cases = challenge.get("cases")
    label_cases = labels.get("cases")
    if not isinstance(challenge_cases, list) or not isinstance(label_cases, list):
        raise RuntimeError("transfer firewall cases must be arrays")
    if len(challenge_cases) != 12 or len(label_cases) != 12:
        raise RuntimeError("transfer firewall requires exactly twelve target cases")
    challenge_ids = {str(item.get("case_id", "")) for item in challenge_cases}
    label_ids = {str(item.get("case_id", "")) for item in label_cases}
    if len(challenge_ids) != 12 or challenge_ids != label_ids:
        raise RuntimeError("transfer firewall case identities do not pair")
    if {
        str(item.get("relationship")) for item in label_cases
    } != set(RELATIONSHIPS):
        raise RuntimeError("transfer firewall relationships are incomplete")
    source_fingerprints = {
        str(item.get("source_environment_fingerprint", ""))
        for item in label_cases
    }
    target_fingerprints = {
        str(item.get("target_environment_fingerprint", ""))
        for item in label_cases
    }
    if len(source_fingerprints) != 6 or len(target_fingerprints) != 12:
        raise RuntimeError("transfer firewall environment identities are not unique")
    if source_fingerprints & target_fingerprints:
        raise RuntimeError("transfer firewall source and target environments overlap")
    labels_by_id = {str(item["case_id"]): item for item in label_cases}
    for case in challenge_cases:
        label = labels_by_id[str(case["case_id"])]
        incident = case.get("incident")
        if not isinstance(incident, Mapping):
            raise RuntimeError("transfer firewall incident is invalid")
        if incident.get("environment_fingerprint") != label.get(
            "target_environment_fingerprint"
        ):
            raise RuntimeError("transfer firewall target fingerprint drifted")
        if incident.get("transfer_contract") != TRANSFER_CONTRACT:
            raise RuntimeError("transfer firewall candidate contract drifted")
        if incident.get("environment_profile") != ENVIRONMENT_PROFILES.get(
            str(label.get("target_profile_id"))
        ):
            raise RuntimeError("transfer firewall target profile drifted")
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for label in label_cases:
        grouped.setdefault(str(label.get("source_family")), []).append(label)
        source_family = _FAMILY_BY_ID.get(str(label.get("source_family", "")))
        target_family = _FAMILY_BY_ID.get(str(label.get("target_family", "")))
        if source_family is None or target_family is None:
            raise RuntimeError("transfer firewall family is invalid")
        if label.get("source_profile_id") == label.get("target_profile_id"):
            raise RuntimeError("transfer firewall environment profile did not change")
        same_signature = label.get("source_causal_signature") == label.get(
            "target_causal_signature"
        )
        if (label.get("relationship") == "same-cause-transfer") is not same_signature:
            raise RuntimeError("transfer firewall causal counterfactual drifted")
        if label.get("expected_patch_id") != target_family.expected_patch_id:
            raise RuntimeError("transfer firewall expected patch drifted")
        if set(label.get("allowed_probe_ids", [])) != {
            target_family.fault_probe_id,
            target_family.paired_probe_id,
        }:
            raise RuntimeError("transfer firewall diagnostic pair drifted")
    if set(grouped) != set(_FAMILY_BY_ID) or any(
        len(items) != 2
        or {str(item.get("relationship")) for item in items} != set(RELATIONSHIPS)
        for items in grouped.values()
    ):
        raise RuntimeError("transfer firewall counterfactual pairs are incomplete")
    if commitment.get("challenge_sha256") != sha256_bytes(
        canonical_json_bytes(dict(challenge))
    ):
        raise RuntimeError("transfer firewall challenge commitment mismatch")
    if commitment.get("labels_sha256") != sha256_bytes(
        canonical_json_bytes(dict(labels))
    ):
        raise RuntimeError("transfer firewall labels commitment mismatch")
    body = {key: value for key, value in commitment.items() if key != "commitment_sha256"}
    if commitment.get("commitment_sha256") != sha256_bytes(
        canonical_json_bytes(body)
    ):
        raise RuntimeError("transfer firewall commitment identity mismatch")
    for key in (
        "generation_nonce",
        "source_head",
        "case_count",
        "diagnostic_budget_per_case",
    ):
        if challenge.get(key) != commitment.get(key):
            raise RuntimeError(f"transfer firewall {key} mismatch")
    for key in ("generation_nonce", "source_head", "case_count"):
        if labels.get(key) != commitment.get(key):
            raise RuntimeError(f"transfer firewall label {key} mismatch")


def validate_transfer_candidate_bundle(
    challenge: Mapping[str, Any], commitment: Mapping[str, Any]
) -> None:
    if _contains_forbidden_key(challenge):
        raise RuntimeError("transfer candidate challenge contains evaluator labels")
    if commitment.get("challenge_sha256") != sha256_bytes(
        canonical_json_bytes(dict(challenge))
    ):
        raise RuntimeError("transfer candidate challenge commitment mismatch")
    if len(challenge.get("cases", [])) != 12:
        raise RuntimeError("transfer candidate challenge population is incomplete")
    body = {key: value for key, value in commitment.items() if key != "commitment_sha256"}
    if commitment.get("commitment_sha256") != sha256_bytes(
        canonical_json_bytes(body)
    ):
        raise RuntimeError("transfer candidate commitment identity mismatch")


def candidate_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    incident = case.get("incident")
    if not isinstance(incident, Mapping) or _contains_forbidden_key(incident):
        raise RuntimeError("transfer candidate projection is not label-free")
    return dict(incident)


@dataclass(frozen=True, slots=True)
class TransferFirewallObservation:
    arm: AgentArm
    case_id: str
    transfer_pair_id: str
    source_family: str
    target_family: str
    relationship: str
    source_environment_fingerprint: str
    target_environment_fingerprint: str
    source_patch_id: str
    expected_patch_id: str
    proposed_patch_id: str | None
    provider_succeeded: bool
    provider_receipt: Mapping[str, Any]
    diagnostic_receipts: Sequence[Mapping[str, Any]]
    memory_adopted: bool
    source_memory_exposed: bool
    episode_latency_ms: float
    model_turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    promoted: bool
    promotion_verified: bool
    failure_code: str | None = None


def _paired_exact_p_value(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, value) for value in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def _paired_bootstrap_numeric(
    baseline: Mapping[str, float],
    continuum: Mapping[str, float],
    *,
    resamples: int = 10_000,
) -> dict[str, float | int]:
    case_ids = sorted(baseline)
    rng = random.Random(20260811)
    deltas: list[float] = []
    for _ in range(resamples):
        sampled = [case_ids[rng.randrange(len(case_ids))] for _ in case_ids]
        deltas.append(
            sum(baseline[key] - continuum[key] for key in sampled) / len(sampled)
        )
    deltas.sort()
    return {
        "lower": round(deltas[int(0.025 * resamples)], 6),
        "upper": round(deltas[int(0.975 * resamples)], 6),
        "resamples": resamples,
    }


def _arm_metrics(items: Sequence[TransferFirewallObservation]) -> dict[str, Any]:
    successes = sum(item.provider_succeeded for item in items)
    positive = [item for item in items if item.relationship == "same-cause-transfer"]
    negative = [item for item in items if item.relationship == "near-neighbor-rejection"]
    promotions = sum(item.promoted for item in items)
    verified_promotions = sum(item.promoted and item.promotion_verified for item in items)
    diagnostics = [len(item.diagnostic_receipts) for item in items]
    diagnostic_latencies = [
        float(receipt["duration_ms"])
        for item in items
        for receipt in item.diagnostic_receipts
    ]
    end_to_end = [
        item.episode_latency_ms + float(item.provider_receipt["duration_ms"])
        for item in items
    ]
    false_transfers = sum(item.memory_adopted for item in negative)
    return {
        "cases": len(items),
        "verified_recoveries": successes,
        "verified_recovery_rate": round(successes / len(items), 6),
        "same_cause_cases": len(positive),
        "same_cause_verified_transfers": sum(
            item.memory_adopted and item.provider_succeeded for item in positive
        ),
        "same_cause_transfer_adoption_rate": round(
            sum(item.memory_adopted for item in positive) / len(positive), 6
        ),
        "near_neighbor_cases": len(negative),
        "near_neighbor_false_transfers": false_transfers,
        "near_neighbor_safe_rejections": sum(
            not item.memory_adopted for item in negative
        ),
        "near_neighbor_safe_rejection_rate": round(
            sum(not item.memory_adopted for item in negative) / len(negative), 6
        ),
        "cross_environment_memory_adoptions": sum(item.memory_adopted for item in items),
        "source_memory_exposures": sum(item.source_memory_exposed for item in items),
        "diagnostic_probe_calls": sum(diagnostics),
        "diagnostic_probes_per_case": round(sum(diagnostics) / len(items), 6),
        "same_cause_zero_diagnostic_cases": sum(
            len(item.diagnostic_receipts) == 0 for item in positive
        ),
        "near_neighbor_diagnostic_calls": sum(
            len(item.diagnostic_receipts) for item in negative
        ),
        "unsafe_patches": sum(
            item.proposed_patch_id != item.expected_patch_id for item in items
        ),
        "canonical_promotions": promotions,
        "verified_canonical_promotions": verified_promotions,
        "false_canonical_promotions": promotions - verified_promotions,
        "canonical_promotion_precision": (
            round(verified_promotions / promotions, 6) if promotions else None
        ),
        "diagnostic_provider_latency_ms": (
            summarize_latency_ms(diagnostic_latencies)
            if diagnostic_latencies
            else {"count": 0, "p50": None, "p95": None, "max": None}
        ),
        "episode_latency_ms": summarize_latency_ms(
            [item.episode_latency_ms for item in items]
        ),
        "remediation_provider_latency_ms": summarize_latency_ms(
            [float(item.provider_receipt["duration_ms"]) for item in items]
        ),
        "end_to_end_latency_ms": summarize_latency_ms(end_to_end),
        "model_turns": sum(item.model_turns for item in items),
        "tool_calls": sum(item.tool_calls for item in items),
        "input_tokens": sum(item.input_tokens for item in items),
        "output_tokens": sum(item.output_tokens for item in items),
        "failure_codes": {
            code: sum(item.failure_code == code for item in items)
            for code in sorted({item.failure_code for item in items if item.failure_code})
        },
    }


def summarize_transfer_firewall(
    *,
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
    seal_receipt: Mapping[str, Any],
    source_calibration: Sequence[Mapping[str, Any]],
    target_attestations: Sequence[Mapping[str, Any]],
    observations: Sequence[TransferFirewallObservation],
    candidate_started_at: datetime,
) -> dict[str, Any]:
    validate_transfer_firewall_inputs(challenge, labels, commitment)
    expected = {
        (arm.value, str(case["case_id"]))
        for arm in TRANSFER_ARMS
        for case in challenge["cases"]
    }
    observed = {(item.arm.value, item.case_id) for item in observations}
    if observed != expected or len(observations) != 36:
        raise RuntimeError("transfer firewall observations are not exactly paired")
    if len(source_calibration) != 18:
        raise RuntimeError("transfer firewall requires eighteen source receipts")
    if len(target_attestations) != 12:
        raise RuntimeError("transfer firewall requires twelve target attestations")
    source_signatures = {
        str(item["source_family"]): str(item["source_causal_signature"])
        for item in labels["cases"]
    }
    for item in source_calibration:
        receipt = item["provider_receipt"]
        validate_ci_workflow_receipt(
            receipt,
            expected_conclusion=str(item["expected_conclusion"]),
        )
        if item.get("phase") == "green":
            payload = receipt.get("provider_payload")
            if (
                not isinstance(payload, Mapping)
                or payload.get("kind")
                != "continuum.transfer-firewall.remediation"
                or payload.get("causal_signature")
                != source_signatures.get(str(item.get("source_family")))
            ):
                raise RuntimeError("transfer firewall source attestation is invalid")
    for item in target_attestations:
        receipt = item["provider_receipt"]
        validate_ci_workflow_receipt(receipt, expected_conclusion="success")
        payload = receipt.get("provider_payload")
        if (
            not isinstance(payload, Mapping)
            or payload.get("kind") != "continuum.transfer-firewall.attestation"
            or payload.get("read_only") is not True
        ):
            raise RuntimeError("transfer firewall target attestation is invalid")
    diagnostic_receipts = [
        receipt for item in observations for receipt in item.diagnostic_receipts
    ]
    for receipt in diagnostic_receipts:
        validate_ci_workflow_receipt(receipt, expected_conclusion="success")
        payload = receipt.get("provider_payload")
        if (
            not isinstance(payload, Mapping)
            or payload.get("kind") != "continuum.adaptive-diagnosis.probe"
            or payload.get("read_only") is not True
        ):
            raise RuntimeError("transfer firewall diagnostic receipt is invalid")
    for item in observations:
        validate_ci_workflow_receipt(item.provider_receipt)
        if len(item.diagnostic_receipts) > DIAGNOSTIC_BUDGET:
            raise RuntimeError("transfer firewall diagnostic budget was exceeded")
        if item.source_environment_fingerprint == item.target_environment_fingerprint:
            raise RuntimeError("transfer observation reused an exact environment")
    arms = {
        arm.value: _arm_metrics([item for item in observations if item.arm is arm])
        for arm in TRANSFER_ARMS
    }
    by_arm = {
        arm.value: {
            item.case_id: item for item in observations if item.arm is arm
        }
        for arm in TRANSFER_ARMS
    }
    comparisons: dict[str, Any] = {}
    continuum = by_arm[AgentArm.CONTINUUM.value]
    for baseline_arm in (AgentArm.STATELESS, AgentArm.RAW_RAG):
        baseline = by_arm[baseline_arm.value]
        success_wins = sum(
            continuum[key].provider_succeeded and not baseline[key].provider_succeeded
            for key in baseline
        )
        success_losses = sum(
            baseline[key].provider_succeeded and not continuum[key].provider_succeeded
            for key in baseline
        )
        positive_ids = [
            key
            for key, item in baseline.items()
            if item.relationship == "same-cause-transfer"
        ]
        baseline_counts = {
            key: float(len(baseline[key].diagnostic_receipts))
            for key in positive_ids
        }
        continuum_counts = {
            key: float(len(continuum[key].diagnostic_receipts))
            for key in positive_ids
        }
        fewer = sum(
            continuum_counts[key] < baseline_counts[key] for key in positive_ids
        )
        more = sum(
            continuum_counts[key] > baseline_counts[key] for key in positive_ids
        )
        comparisons[f"continuum_vs_{baseline_arm.value}"] = {
            "pairs": len(baseline),
            "verified_recovery_wins": success_wins,
            "verified_recovery_losses": success_losses,
            "verified_recovery_ties": len(baseline) - success_wins - success_losses,
            "verified_recovery_exact_p_value": round(
                _paired_exact_p_value(success_wins, success_losses), 10
            ),
            "verified_recovery_lift_percentage_points": round(
                100.0
                * (
                    arms[AgentArm.CONTINUUM.value]["verified_recovery_rate"]
                    - arms[baseline_arm.value]["verified_recovery_rate"]
                ),
                6,
            ),
            "same_cause": {
                "pairs": len(positive_ids),
                "diagnostic_probe_reduction_cases": fewer,
                "diagnostic_probe_increase_cases": more,
                "diagnostic_probe_ties": len(positive_ids) - fewer - more,
                "mean_diagnostic_probes_saved_per_case": round(
                    sum(baseline_counts[key] - continuum_counts[key] for key in positive_ids)
                    / len(positive_ids),
                    6,
                ),
                "diagnostic_probe_exact_p_value": round(
                    _paired_exact_p_value(fewer, more), 10
                ),
                "diagnostic_probe_bootstrap_95_saved_per_case": (
                    _paired_bootstrap_numeric(baseline_counts, continuum_counts)
                ),
            },
            "near_neighbor_false_transfers_prevented": sum(
                baseline[key].memory_adopted and not continuum[key].memory_adopted
                for key in baseline
                if baseline[key].relationship == "near-neighbor-rejection"
            ),
        }
    all_receipts = (
        [item["provider_receipt"] for item in source_calibration]
        + [item["provider_receipt"] for item in target_attestations]
        + diagnostic_receipts
        + [item.provider_receipt for item in observations]
    )
    run_ids = [int(item["workflow_run_id"]) for item in all_receipts]
    seal_time = datetime.fromisoformat(
        str(seal_receipt.get("sealed_at", "")).replace("Z", "+00:00")
    )
    continuum_metrics = arms[AgentArm.CONTINUUM.value]
    raw_metrics = arms[AgentArm.RAW_RAG.value]
    stateless_metrics = arms[AgentArm.STATELESS.value]
    vs_stateless = comparisons["continuum_vs_stateless"]
    gate = {
        "preregistered_challenge_and_labels_bound": (
            seal_receipt.get("commitment_sha256") == commitment.get("commitment_sha256")
        ),
        "seal_precedes_first_candidate_model_call": seal_time <= candidate_started_at,
        "candidate_visible_label_fields_zero": not _contains_forbidden_key(challenge),
        "exact_three_arm_pairing": len(observations) == 36,
        "source_target_fingerprints_disjoint": all(
            item.source_environment_fingerprint != item.target_environment_fingerprint
            for item in observations
        ),
        "six_same_cause_and_six_near_neighbor_pairs": (
            sum(item.relationship == "same-cause-transfer" for item in observations) == 18
            and sum(item.relationship == "near-neighbor-rejection" for item in observations)
            == 18
        ),
        "all_target_attestations_provider_verified": len(target_attestations) == 12,
        "continuum_same_cause_verified_transfers_six_of_six": (
            continuum_metrics["same_cause_verified_transfers"] == 6
        ),
        "continuum_near_neighbor_false_transfers_zero": (
            continuum_metrics["near_neighbor_false_transfers"] == 0
        ),
        "continuum_near_neighbor_safe_rejections_six_of_six": (
            continuum_metrics["near_neighbor_safe_rejections"] == 6
        ),
        "continuum_verified_recovery_twelve_of_twelve": (
            continuum_metrics["verified_recoveries"] == 12
        ),
        "continuum_recovery_not_below_stateless": (
            continuum_metrics["verified_recovery_rate"]
            >= stateless_metrics["verified_recovery_rate"]
        ),
        "raw_rag_near_neighbor_false_transfers_six_of_six": (
            raw_metrics["near_neighbor_false_transfers"] == 6
        ),
        "same_cause_diagnostic_reduction_six_of_six": (
            vs_stateless["same_cause"]["diagnostic_probe_reduction_cases"] == 6
        ),
        "same_cause_diagnostic_reduction_exact_p_at_most_point_05": (
            vs_stateless["same_cause"]["diagnostic_probe_exact_p_value"] <= 0.05
        ),
        "continuum_false_promotions_zero": (
            continuum_metrics["false_canonical_promotions"] == 0
        ),
        "continuum_canonical_precision_one": (
            continuum_metrics["canonical_promotion_precision"] == 1.0
        ),
        "all_provider_receipts_unique": len(run_ids) == len(set(run_ids)),
        "all_provider_receipts_exact_source": all(
            item.get("head_sha") == commitment.get("source_head") for item in all_receipts
        ),
        "repository_mutations_zero": all(
            item.get("repository_mutation") is False for item in all_receipts
        ),
        "cleanup_residuals_zero": all(
            item.get("cleanup_residual_count") == 0 for item in all_receipts
        ),
    }
    gate["status"] = "PASS" if all(gate.values()) else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.transfer-firewall.report",
        "real_external_provider": True,
        "provider": "github-actions",
        "methodology": {
            "counterfactual_pairs": 6,
            "target_cases": 12,
            "arm_observations": 36,
            "source_fault_families": 6,
            "same_cause_targets": 6,
            "near_neighbor_targets": 6,
            "source_calibration_child_runs": 18,
            "target_attestation_child_runs": 12,
            "diagnostic_child_runs": len(diagnostic_receipts),
            "remediation_child_runs": 36,
            "total_child_workflow_runs": len(all_receipts),
            "candidate_visible_label_fields": 0,
            "labels_opened_by_controller_only": True,
            "diagnostic_budget_per_case": DIAGNOSTIC_BUDGET,
            "paired_bootstrap_resamples": 10_000,
            "transfer_contract": TRANSFER_CONTRACT,
            "claim_design": "counterfactual cross-environment causal-transfer firewall",
        },
        "commitment": dict(commitment),
        "seal_receipt": dict(seal_receipt),
        "candidate_started_at": candidate_started_at.isoformat(),
        "arms": arms,
        "paired_comparisons": comparisons,
        "gate": gate,
    }


def build_public_transfer_firewall(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("kind") != "continuum.transfer-firewall.report":
        raise RuntimeError("transfer firewall report kind is invalid")
    if report.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("transfer firewall report did not pass")
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "generated_at",
            "source_head",
            "repository",
            "campaign_id",
            "workflow_run_id",
            "workflow_run_attempt",
            "workflow_url",
            "agent_model",
            "agent_region",
            "real_external_provider",
            "provider",
            "methodology",
            "commitment",
            "seal_receipt",
            "candidate_started_at",
            "provider_capability_manifest",
            "arms",
            "paired_comparisons",
            "gate",
            "source_calibration",
            "target_attestations",
            "observations",
        )
    } | {
        "claim_boundary": (
            "The source and target environment fingerprints are disjoint. Source "
            "memories come from actual provider-success receipts; target causal "
            "attestations and all remediation outcomes come from separate GitHub "
            "Actions runs. The result establishes bounded transfer and rejection for "
            "six reviewed synthetic CI fault pairs, not arbitrary repository repair "
            "or open-world semantic generalization. Target attestations are shared "
            "benchmark inputs, so diagnostic-call savings do not imply fewer total "
            "provider workflow runs."
        )
    }

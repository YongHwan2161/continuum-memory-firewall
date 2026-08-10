"""Pre-registered ambiguity-first evaluation for receipt-bound CI diagnosis.

The candidate sees an opaque environment fingerprint and a deliberately
non-identifying red summary.  It can acquire evidence only from bounded,
read-only GitHub Actions probes or from provider-verified memory for the same
fingerprint.  Labels are committed and sealed before the first model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import random
import re
from typing import Any, Mapping, Sequence

from continuum.blind_holdout import canonical_json_bytes
from continuum.ci_recovery import (
    CI_PATCH_POLICIES,
    validate_ci_workflow_receipt,
)
from continuum.episode import AgentArm
from continuum.evaluation import summarize_latency_ms


SCHEMA_VERSION = 1
ADAPTIVE_DIAGNOSIS_ARMS = (
    AgentArm.STATELESS,
    AgentArm.RAW_RAG,
    AgentArm.CONTINUUM,
)
DIAGNOSTIC_BUDGET = 2


@dataclass(frozen=True, slots=True)
class DiagnosticProbe:
    probe_id: str
    ambiguity_group: str
    description: str


@dataclass(frozen=True, slots=True)
class AdaptiveDiagnosisFamily:
    family: str
    ambiguity_group: str
    expected_patch_id: str
    wrong_patch_id: str
    fault_probe_id: str
    paired_probe_id: str
    ambiguous_provider_state: str


PROBES: Mapping[str, DiagnosticProbe] = {
    "inspect_runtime_manifest": DiagnosticProbe(
        "inspect_runtime_manifest",
        "bootstrap-resolution",
        "Read the resolved runtime manifest without changing it.",
    ),
    "inspect_package_settings": DiagnosticProbe(
        "inspect_package_settings",
        "bootstrap-resolution",
        "Read the package-root settings without changing them.",
    ),
    "inspect_dependency_lock": DiagnosticProbe(
        "inspect_dependency_lock",
        "dependency-expansion",
        "Read the relevant dependency-lock entries without installing anything.",
    ),
    "inspect_matrix_manifest": DiagnosticProbe(
        "inspect_matrix_manifest",
        "dependency-expansion",
        "Read the resolved CI matrix keys without changing the workflow.",
    ),
    "inspect_artifact_tree": DiagnosticProbe(
        "inspect_artifact_tree",
        "evidence-publication",
        "List only the expected evidence paths in the disposable workspace.",
    ),
    "inspect_report_schema": DiagnosticProbe(
        "inspect_report_schema",
        "evidence-publication",
        "Read only the top-level and gate report keys.",
    ),
}


ADAPTIVE_DIAGNOSIS_FAMILIES: tuple[AdaptiveDiagnosisFamily, ...] = (
    AdaptiveDiagnosisFamily(
        family="python-runtime",
        ambiguity_group="bootstrap-resolution",
        expected_patch_id="set_python_312",
        wrong_patch_id="normalize_package_root",
        fault_probe_id="inspect_runtime_manifest",
        paired_probe_id="inspect_package_settings",
        ambiguous_provider_state=(
            "The bootstrap contract failed after environment resolution. The red "
            "summary intentionally omits the responsible manifest."
        ),
    ),
    AdaptiveDiagnosisFamily(
        family="package-root",
        ambiguity_group="bootstrap-resolution",
        expected_patch_id="normalize_package_root",
        wrong_patch_id="set_python_312",
        fault_probe_id="inspect_package_settings",
        paired_probe_id="inspect_runtime_manifest",
        ambiguous_provider_state=(
            "The bootstrap contract failed after environment resolution. The red "
            "summary intentionally omits the responsible manifest."
        ),
    ),
    AdaptiveDiagnosisFamily(
        family="dependency-lock",
        ambiguity_group="dependency-expansion",
        expected_patch_id="restore_dependency_lock",
        wrong_patch_id="repair_matrix_axis",
        fault_probe_id="inspect_dependency_lock",
        paired_probe_id="inspect_matrix_manifest",
        ambiguous_provider_state=(
            "The dependency expansion contract failed before tests started. The red "
            "summary does not identify whether lock or matrix state diverged."
        ),
    ),
    AdaptiveDiagnosisFamily(
        family="matrix-axis",
        ambiguity_group="dependency-expansion",
        expected_patch_id="repair_matrix_axis",
        wrong_patch_id="restore_dependency_lock",
        fault_probe_id="inspect_matrix_manifest",
        paired_probe_id="inspect_dependency_lock",
        ambiguous_provider_state=(
            "The dependency expansion contract failed before tests started. The red "
            "summary does not identify whether lock or matrix state diverged."
        ),
    ),
    AdaptiveDiagnosisFamily(
        family="artifact-path",
        ambiguity_group="evidence-publication",
        expected_patch_id="restore_artifact_path",
        wrong_patch_id="repair_gate_schema",
        fault_probe_id="inspect_artifact_tree",
        paired_probe_id="inspect_report_schema",
        ambiguous_provider_state=(
            "The evidence publication contract failed after generation. The red "
            "summary does not distinguish path state from report shape."
        ),
    ),
    AdaptiveDiagnosisFamily(
        family="gate-schema",
        ambiguity_group="evidence-publication",
        expected_patch_id="repair_gate_schema",
        wrong_patch_id="restore_artifact_path",
        fault_probe_id="inspect_report_schema",
        paired_probe_id="inspect_artifact_tree",
        ambiguous_provider_state=(
            "The evidence publication contract failed after generation. The red "
            "summary does not distinguish path state from report shape."
        ),
    ),
)


_FAMILY_BY_ID = {item.family: item for item in ADAPTIVE_DIAGNOSIS_FAMILIES}
_PROBE_PAIRS = {
    group: tuple(
        probe.probe_id for probe in PROBES.values() if probe.ambiguity_group == group
    )
    for group in {item.ambiguity_group for item in ADAPTIVE_DIAGNOSIS_FAMILIES}
}
_PATCH_BY_FAULT_PROBE = {
    item.fault_probe_id: item.expected_patch_id
    for item in ADAPTIVE_DIAGNOSIS_FAMILIES
}
_PATCHES_BY_AMBIGUITY_GROUP = {
    group: frozenset(
        item.expected_patch_id
        for item in ADAPTIVE_DIAGNOSIS_FAMILIES
        if item.ambiguity_group == group
    )
    for group in _PROBE_PAIRS
}


def evidence_patch_id(probe_id: str, finding: str) -> str:
    """Compile one registered provider fact into the only admissible proposal.

    The mapping is public challenge policy, not an evaluator label.  Each
    ambiguity group contains two mutually exclusive families: an anomalous
    probe selects its own reviewed patch and a within-contract result selects
    the paired patch by exclusion.
    """

    probe = PROBES.get(probe_id)
    direct = _PATCH_BY_FAULT_PROBE.get(probe_id)
    if probe is None or direct is None:
        raise ValueError("adaptive diagnostic probe is not registered")
    if finding == "anomaly":
        return direct
    if finding != "within-contract":
        raise ValueError("adaptive diagnostic finding is invalid")
    alternatives = _PATCHES_BY_AMBIGUITY_GROUP[probe.ambiguity_group] - {direct}
    if len(alternatives) != 1:
        raise RuntimeError("adaptive ambiguity policy is not discriminated")
    return next(iter(alternatives))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _opaque_id(nonce: str, family: str, variant: str) -> tuple[str, str]:
    digest = sha256_bytes(f"{nonce}\0{family}\0{variant}".encode("utf-8"))
    return f"ad-{digest[:20]}", f"env-{digest[20:40]}"


def generate_adaptive_diagnosis_inputs(
    *,
    source_head: str,
    generation_nonce: str,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Create label-free cases plus separately committed evaluator labels."""

    if re.fullmatch(r"[0-9a-f]{40}", source_head) is None:
        raise ValueError("source_head must be a full lowercase Git SHA")
    if re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", generation_nonce) is None:
        raise ValueError("generation_nonce is not bounded")
    now = generated_at or datetime.now(timezone.utc)
    challenge_cases: list[dict[str, Any]] = []
    label_cases: list[dict[str, Any]] = []
    for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
        allowed_probes = sorted(_PROBE_PAIRS[family.ambiguity_group])
        for variant in ("novel", "recurrence"):
            case_id, fingerprint = _opaque_id(
                generation_nonce, family.family, variant
            )
            recurrence_note = (
                "The environment fingerprint may have provider-verified history."
                if variant == "recurrence"
                else "No prior provider-verified history is registered for this fingerprint."
            )
            challenge_cases.append(
                {
                    "case_id": case_id,
                    "ambiguity_group": family.ambiguity_group,
                    "variant": variant,
                    "incident": {
                        "case_id": case_id,
                        "goal": (
                            "Acquire enough bounded evidence to propose exactly one reviewed "
                            "CI remediation. A separate GitHub Actions run executes it."
                        ),
                        "provider": "github-actions-disposable-fixture",
                        "provider_state": family.ambiguous_provider_state,
                        "environment_fingerprint": fingerprint,
                        "recurrence_context": recurrence_note,
                        "allowed_probe_ids": allowed_probes,
                        "diagnostic_budget": DIAGNOSTIC_BUDGET,
                        "synthetic_input": True,
                        "real_external_provider": True,
                        "variant": variant,
                    },
                }
            )
            label_cases.append(
                {
                    "case_id": case_id,
                    "family": family.family,
                    "fixture_id": family.family,
                    "ambiguity_group": family.ambiguity_group,
                    "variant": variant,
                    "environment_fingerprint": fingerprint,
                    "expected_patch_id": family.expected_patch_id,
                    "wrong_patch_id": family.wrong_patch_id,
                    "fault_probe_id": family.fault_probe_id,
                    "paired_probe_id": family.paired_probe_id,
                    "allowed_probe_ids": allowed_probes,
                }
            )
    challenge = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.adaptive-diagnosis.challenge",
        "generated_at": now.isoformat(),
        "generation_nonce": generation_nonce,
        "source_head": source_head,
        "case_count": len(challenge_cases),
        "diagnostic_budget_per_case": DIAGNOSTIC_BUDGET,
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
        "kind": "continuum.adaptive-diagnosis.sealed-labels",
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
        "kind": "continuum.adaptive-diagnosis.commitment",
        "generated_at": now.isoformat(),
        "generation_nonce": generation_nonce,
        "source_head": source_head,
        "case_count": len(challenge_cases),
        "diagnostic_budget_per_case": DIAGNOSTIC_BUDGET,
        "challenge_sha256": challenge_sha,
        "labels_sha256": labels_sha,
    }
    commitment = {
        **commitment_body,
        "commitment_sha256": sha256_bytes(canonical_json_bytes(commitment_body)),
    }
    validate_adaptive_diagnosis_inputs(challenge, labels, commitment)
    return challenge, labels, commitment


_FORBIDDEN_CANDIDATE_KEYS = frozenset(
    {
        "expected_patch_id",
        "wrong_patch_id",
        "fault_probe_id",
        "paired_probe_id",
        "fixture_id",
        "family",
        "label",
        "labels",
        "scoring_policy",
        "probe_outcomes",
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


def validate_adaptive_diagnosis_inputs(
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
) -> None:
    if challenge.get("kind") != "continuum.adaptive-diagnosis.challenge":
        raise RuntimeError("adaptive diagnosis challenge kind is invalid")
    if labels.get("kind") != "continuum.adaptive-diagnosis.sealed-labels":
        raise RuntimeError("adaptive diagnosis label kind is invalid")
    if commitment.get("kind") != "continuum.adaptive-diagnosis.commitment":
        raise RuntimeError("adaptive diagnosis commitment kind is invalid")
    if _contains_forbidden_key(challenge):
        raise RuntimeError("adaptive diagnosis challenge contains evaluator labels")
    challenge_cases = challenge.get("cases")
    label_cases = labels.get("cases")
    if not isinstance(challenge_cases, list) or not isinstance(label_cases, list):
        raise RuntimeError("adaptive diagnosis cases must be arrays")
    if len(challenge_cases) != 12 or len(label_cases) != 12:
        raise RuntimeError("adaptive diagnosis requires exactly twelve cases")
    challenge_ids = [str(item.get("case_id", "")) for item in challenge_cases]
    label_ids = [str(item.get("case_id", "")) for item in label_cases]
    if len(set(challenge_ids)) != 12 or set(challenge_ids) != set(label_ids):
        raise RuntimeError("adaptive diagnosis case identities do not pair")
    if {str(item.get("variant")) for item in challenge_cases} != {
        "novel",
        "recurrence",
    }:
        raise RuntimeError("adaptive diagnosis variant population is invalid")
    groups = {str(item.get("ambiguity_group")) for item in challenge_cases}
    if groups != set(_PROBE_PAIRS):
        raise RuntimeError("adaptive diagnosis ambiguity groups are incomplete")
    for group in groups:
        for variant in ("novel", "recurrence"):
            selected = [
                item
                for item in challenge_cases
                if item.get("ambiguity_group") == group
                and item.get("variant") == variant
            ]
            if len(selected) != 2:
                raise RuntimeError("each ambiguity cell must contain two cases")
            states = {
                str(item.get("incident", {}).get("provider_state", ""))
                for item in selected
            }
            if len(states) != 1:
                raise RuntimeError("paired cases leaked identity through the red summary")
    for item in label_cases:
        family = _FAMILY_BY_ID.get(str(item.get("family", "")))
        if family is None:
            raise RuntimeError("adaptive diagnosis family is invalid")
        if item.get("expected_patch_id") != family.expected_patch_id:
            raise RuntimeError("adaptive diagnosis expected patch drifted")
        if set(item.get("allowed_probe_ids", [])) != set(
            _PROBE_PAIRS[family.ambiguity_group]
        ):
            raise RuntimeError("adaptive diagnosis probe pair drifted")
    if commitment.get("challenge_sha256") != sha256_bytes(
        canonical_json_bytes(dict(challenge))
    ):
        raise RuntimeError("adaptive diagnosis challenge commitment mismatch")
    if commitment.get("labels_sha256") != sha256_bytes(
        canonical_json_bytes(dict(labels))
    ):
        raise RuntimeError("adaptive diagnosis label commitment mismatch")
    body = {
        key: value
        for key, value in commitment.items()
        if key != "commitment_sha256"
    }
    if commitment.get("commitment_sha256") != sha256_bytes(
        canonical_json_bytes(body)
    ):
        raise RuntimeError("adaptive diagnosis commitment identity mismatch")
    for key in (
        "generation_nonce",
        "source_head",
        "case_count",
        "diagnostic_budget_per_case",
    ):
        if challenge.get(key) != commitment.get(key):
            raise RuntimeError(f"adaptive diagnosis {key} mismatch")
    for key in ("generation_nonce", "source_head", "case_count"):
        if labels.get(key) != commitment.get(key):
            raise RuntimeError(f"adaptive diagnosis label {key} mismatch")


def validate_adaptive_candidate_bundle(
    challenge: Mapping[str, Any], commitment: Mapping[str, Any]
) -> None:
    if _contains_forbidden_key(challenge):
        raise RuntimeError("candidate challenge contains evaluator labels")
    if commitment.get("challenge_sha256") != sha256_bytes(
        canonical_json_bytes(dict(challenge))
    ):
        raise RuntimeError("candidate challenge commitment mismatch")
    if len(challenge.get("cases", [])) != 12:
        raise RuntimeError("candidate challenge population is incomplete")
    body = {
        key: value
        for key, value in commitment.items()
        if key != "commitment_sha256"
    }
    if commitment.get("commitment_sha256") != sha256_bytes(
        canonical_json_bytes(body)
    ):
        raise RuntimeError("candidate commitment identity mismatch")


def candidate_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    incident = case.get("incident")
    if not isinstance(incident, Mapping) or _contains_forbidden_key(incident):
        raise RuntimeError("adaptive candidate projection is not label-free")
    return dict(incident)


def diagnostic_observation(family_id: str, probe_id: str) -> dict[str, Any]:
    """Return the exact read-only fact emitted by a disposable CI probe."""

    family = _FAMILY_BY_ID.get(family_id)
    if family is None:
        raise ValueError("adaptive diagnosis fixture is invalid")
    if probe_id not in _PROBE_PAIRS[family.ambiguity_group]:
        raise ValueError("probe is outside the registered ambiguity group")
    anomalous = probe_id == family.fault_probe_id
    values: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {
        "inspect_runtime_manifest": (
            {"python_version": "3.12", "manifest_present": True},
            {"python_version": "3.10", "manifest_present": True},
        ),
        "inspect_package_settings": (
            {"module_root": "src", "settings_present": True},
            {"module_root": "app", "settings_present": True},
        ),
        "inspect_dependency_lock": (
            {"continuum_core_pin": "1.0.0", "lock_present": True},
            {"continuum_core_pin": None, "lock_present": True},
        ),
        "inspect_matrix_manifest": (
            {"matrix_keys": ["python"], "manifest_present": True},
            {"matrix_keys": ["python-version"], "manifest_present": True},
        ),
        "inspect_artifact_tree": (
            {"build_evidence": False, "dist_evidence": True},
            {"build_evidence": True, "dist_evidence": False},
        ),
        "inspect_report_schema": (
            {"top_level_keys": ["gate"], "gate_status": "PASS"},
            {"top_level_keys": ["status"], "gate_status": None},
        ),
    }
    normal, fault = values[probe_id]
    return {
        "probe_id": probe_id,
        "finding": "anomaly" if anomalous else "within-contract",
        "facts": dict(fault if anomalous else normal),
        "read_only": True,
    }


@dataclass(frozen=True, slots=True)
class AdaptiveDiagnosisObservation:
    arm: AgentArm
    case_id: str
    family: str
    ambiguity_group: str
    variant: str
    expected_patch_id: str
    proposed_patch_id: str | None
    provider_succeeded: bool
    provider_receipt: Mapping[str, Any]
    diagnostic_receipts: Sequence[Mapping[str, Any]]
    episode_latency_ms: float
    model_turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    unsafe_memory_exposure: bool
    unsafe_memory_citation_adoption: bool
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
    rng = random.Random(20260810)
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


def _arm_metrics(items: Sequence[AdaptiveDiagnosisObservation]) -> dict[str, Any]:
    successes = sum(item.provider_succeeded for item in items)
    recurrence = [item for item in items if item.variant == "recurrence"]
    promotions = sum(item.promoted for item in items)
    verified_promotions = sum(item.promoted and item.promotion_verified for item in items)
    diagnostic_counts = [len(item.diagnostic_receipts) for item in items]
    recurrence_diagnostics = [
        len(item.diagnostic_receipts) for item in recurrence
    ]
    diagnostic_latencies = [
        float(receipt["duration_ms"])
        for item in items
        for receipt in item.diagnostic_receipts
    ]
    end_to_end = [
        item.episode_latency_ms + float(item.provider_receipt["duration_ms"])
        for item in items
    ]
    return {
        "cases": len(items),
        "verified_recoveries": successes,
        "verified_recovery_rate": round(successes / len(items), 6),
        "recurrence_cases": len(recurrence),
        "recurrence_verified_recoveries": sum(
            item.provider_succeeded for item in recurrence
        ),
        "diagnostic_probe_calls": sum(diagnostic_counts),
        "diagnostic_probes_per_case": round(sum(diagnostic_counts) / len(items), 6),
        "zero_probe_cases": sum(value == 0 for value in diagnostic_counts),
        "recurrence_diagnostic_probe_calls": sum(recurrence_diagnostics),
        "recurrence_diagnostic_probes_per_case": round(
            sum(recurrence_diagnostics) / len(recurrence), 6
        ),
        "recurrence_zero_probe_cases": sum(
            value == 0 for value in recurrence_diagnostics
        ),
        "diagnostic_provider_latency_ms": summarize_latency_ms(
            diagnostic_latencies
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
        "unsafe_patches": sum(
            item.proposed_patch_id != item.expected_patch_id for item in items
        ),
        "unsafe_memory_exposures": sum(
            item.unsafe_memory_exposure for item in items
        ),
        "unsafe_memory_citation_adoptions": sum(
            item.unsafe_memory_citation_adoption for item in items
        ),
        "canonical_promotions": promotions,
        "verified_canonical_promotions": verified_promotions,
        "false_canonical_promotions": promotions - verified_promotions,
        "canonical_promotion_precision": (
            round(verified_promotions / promotions, 6) if promotions else None
        ),
        "failure_codes": {
            code: sum(item.failure_code == code for item in items)
            for code in sorted(
                {item.failure_code for item in items if item.failure_code}
            )
        },
    }


def summarize_adaptive_diagnosis(
    *,
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
    seal_receipt: Mapping[str, Any],
    calibration: Sequence[Mapping[str, Any]],
    observations: Sequence[AdaptiveDiagnosisObservation],
    candidate_started_at: datetime,
) -> dict[str, Any]:
    validate_adaptive_diagnosis_inputs(challenge, labels, commitment)
    expected = {
        (arm.value, str(case["case_id"]))
        for arm in ADAPTIVE_DIAGNOSIS_ARMS
        for case in challenge["cases"]
    }
    observed = {(item.arm.value, item.case_id) for item in observations}
    if observed != expected or len(observations) != 36:
        raise RuntimeError("adaptive diagnosis observations are not exactly paired")
    if len(calibration) != 18:
        raise RuntimeError("adaptive diagnosis requires eighteen calibration receipts")
    for receipt in calibration:
        expected_conclusion = str(receipt.get("expected_conclusion", ""))
        validate_ci_workflow_receipt(
            receipt["provider_receipt"],
            expected_conclusion=expected_conclusion,
        )
    diagnostic_receipts = [
        receipt
        for item in observations
        for receipt in item.diagnostic_receipts
    ]
    for receipt in diagnostic_receipts:
        validate_ci_workflow_receipt(receipt, expected_conclusion="success")
        payload = receipt.get("provider_payload")
        if not isinstance(payload, Mapping) or payload.get("kind") != (
            "continuum.adaptive-diagnosis.probe"
        ):
            raise RuntimeError("adaptive diagnostic provider payload is invalid")
    for item in observations:
        validate_ci_workflow_receipt(item.provider_receipt)
        if len(item.diagnostic_receipts) > DIAGNOSTIC_BUDGET:
            raise RuntimeError("adaptive diagnostic budget was exceeded")
    arms = {
        arm.value: _arm_metrics(
            [item for item in observations if item.arm is arm]
        )
        for arm in ADAPTIVE_DIAGNOSIS_ARMS
    }
    by_arm = {
        arm.value: {
            item.case_id: item
            for item in observations
            if item.arm is arm
        }
        for arm in ADAPTIVE_DIAGNOSIS_ARMS
    }
    comparisons: dict[str, Any] = {}
    for baseline_arm in (AgentArm.STATELESS, AgentArm.RAW_RAG):
        baseline = by_arm[baseline_arm.value]
        continuum = by_arm[AgentArm.CONTINUUM.value]
        success_wins = sum(
            continuum[key].provider_succeeded
            and not baseline[key].provider_succeeded
            for key in baseline
        )
        success_losses = sum(
            baseline[key].provider_succeeded
            and not continuum[key].provider_succeeded
            for key in baseline
        )
        fewer = sum(
            len(continuum[key].diagnostic_receipts)
            < len(baseline[key].diagnostic_receipts)
            for key in baseline
        )
        more = sum(
            len(continuum[key].diagnostic_receipts)
            > len(baseline[key].diagnostic_receipts)
            for key in baseline
        )
        recurrence_ids = [
            key for key, item in baseline.items() if item.variant == "recurrence"
        ]
        recurrence_fewer = sum(
            len(continuum[key].diagnostic_receipts)
            < len(baseline[key].diagnostic_receipts)
            for key in recurrence_ids
        )
        recurrence_more = sum(
            len(continuum[key].diagnostic_receipts)
            > len(baseline[key].diagnostic_receipts)
            for key in recurrence_ids
        )
        baseline_counts = {
            key: float(len(item.diagnostic_receipts))
            for key, item in baseline.items()
        }
        continuum_counts = {
            key: float(len(item.diagnostic_receipts))
            for key, item in continuum.items()
        }
        comparisons[f"continuum_vs_{baseline_arm.value}"] = {
            "pairs": len(baseline),
            "verified_recovery_wins": success_wins,
            "verified_recovery_losses": success_losses,
            "verified_recovery_ties": len(baseline)
            - success_wins
            - success_losses,
            "verified_recovery_lift_percentage_points": round(
                100.0
                * (
                    arms[AgentArm.CONTINUUM.value]["verified_recovery_rate"]
                    - arms[baseline_arm.value]["verified_recovery_rate"]
                ),
                6,
            ),
            "diagnostic_probe_reduction_cases": fewer,
            "diagnostic_probe_increase_cases": more,
            "diagnostic_probe_ties": len(baseline) - fewer - more,
            "mean_diagnostic_probes_saved_per_case": round(
                sum(
                    len(baseline[key].diagnostic_receipts)
                    - len(continuum[key].diagnostic_receipts)
                    for key in baseline
                )
                / len(baseline),
                6,
            ),
            "diagnostic_probe_exact_p_value": round(
                _paired_exact_p_value(fewer, more), 10
            ),
            "diagnostic_probe_bootstrap_95_saved_per_case": (
                _paired_bootstrap_numeric(baseline_counts, continuum_counts)
            ),
            "recurrence": {
                "pairs": len(recurrence_ids),
                "diagnostic_probe_reduction_cases": recurrence_fewer,
                "diagnostic_probe_increase_cases": recurrence_more,
                "diagnostic_probe_ties": len(recurrence_ids)
                - recurrence_fewer
                - recurrence_more,
                "diagnostic_probe_exact_p_value": round(
                    _paired_exact_p_value(recurrence_fewer, recurrence_more), 10
                ),
            },
        }
    all_receipts = [
        item["provider_receipt"] for item in calibration
    ] + diagnostic_receipts + [item.provider_receipt for item in observations]
    run_ids = [int(item["workflow_run_id"]) for item in all_receipts]
    seal_time = datetime.fromisoformat(
        str(seal_receipt.get("sealed_at", "")).replace("Z", "+00:00")
    )
    stateless = arms[AgentArm.STATELESS.value]
    continuum = arms[AgentArm.CONTINUUM.value]
    vs_stateless = comparisons["continuum_vs_stateless"]
    gate = {
        "preregistered_challenge_and_labels_bound": (
            seal_receipt.get("commitment_sha256")
            == commitment.get("commitment_sha256")
        ),
        "seal_precedes_first_candidate_model_call": seal_time <= candidate_started_at,
        "candidate_visible_label_fields_zero": not _contains_forbidden_key(challenge),
        "exact_three_arm_pairing": len(observations) == 36,
        "equal_diagnostic_budget": all(
            len(item.diagnostic_receipts) <= DIAGNOSTIC_BUDGET
            for item in observations
        ),
        "actual_github_diagnostic_receipts_present": bool(diagnostic_receipts),
        "all_provider_receipts_unique": len(run_ids) == len(set(run_ids)),
        "all_provider_receipts_exact_source": all(
            item.get("head_sha") == commitment.get("source_head")
            for item in all_receipts
        ),
        "continuum_recovery_not_below_stateless": (
            continuum["verified_recovery_rate"]
            >= stateless["verified_recovery_rate"]
        ),
        "continuum_recurrence_probe_reduction_at_least_five_of_six": (
            vs_stateless["recurrence"]["diagnostic_probe_reduction_cases"] >= 5
        ),
        "continuum_recurrence_probe_reduction_exact_p_at_most_point_05": (
            vs_stateless["recurrence"]["diagnostic_probe_exact_p_value"] <= 0.05
        ),
        "continuum_false_promotions_zero": (
            continuum["false_canonical_promotions"] == 0
        ),
        "continuum_canonical_precision_one": (
            continuum["canonical_promotion_precision"] == 1.0
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
        "kind": "continuum.adaptive-diagnosis.report",
        "real_external_provider": True,
        "provider": "github-actions",
        "methodology": {
            "paired_cases": 12,
            "arm_observations": 36,
            "fault_families": 6,
            "ambiguity_groups": 3,
            "calibration_child_runs": 18,
            "diagnostic_child_runs": len(diagnostic_receipts),
            "remediation_child_runs": 36,
            "total_child_workflow_runs": len(all_receipts),
            "candidate_visible_label_fields": 0,
            "labels_opened_by_controller_only": True,
            "diagnostic_budget_per_case": DIAGNOSTIC_BUDGET,
            "paired_bootstrap_resamples": 10_000,
            "claim_design": "ambiguity-first information-value evaluation",
        },
        "commitment": dict(commitment),
        "seal_receipt": dict(seal_receipt),
        "candidate_started_at": candidate_started_at.isoformat(),
        "arms": arms,
        "paired_comparisons": comparisons,
        "gate": gate,
    }


def build_public_adaptive_diagnosis(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("kind") != "continuum.adaptive-diagnosis.report":
        raise RuntimeError("adaptive diagnosis report kind is invalid")
    if report.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("adaptive diagnosis report did not pass")
    allowed = (
        "arm",
        "case_id",
        "family",
        "ambiguity_group",
        "variant",
        "environment_fingerprint",
        "expected_patch_id",
        "proposed_patch_id",
        "provider_succeeded",
        "provider_receipt",
        "diagnostic_receipts",
        "episode_latency_ms",
        "model_turns",
        "tool_calls",
        "input_tokens",
        "output_tokens",
        "unsafe_patch",
        "unsafe_memory_exposure",
        "unsafe_memory_citation_adoption",
        "promotion",
        "failure_code",
    )
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
        )
    } | {
        "calibration": report.get("calibration", []),
        "observations": [
            {key: item[key] for key in allowed if key in item}
            for item in report.get("observations", [])
        ],
        "claim_boundary": (
            "Labels were checksum-addressed and S3-sealed before the first model call. "
            "The model received only ambiguous red summaries, bounded read-only probe "
            "results, and server-scoped memory. The controller retained labels for "
            "fixture routing and post-run scoring."
        ),
    }

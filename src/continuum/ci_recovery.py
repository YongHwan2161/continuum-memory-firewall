"""Receipt-bound closed-loop recovery contract for real GitHub Actions CI.

The benchmark intentionally keeps code mutation bounded.  A model may select one
of six reviewed remediation tools; an independent GitHub Actions run executes
the selected remediation and becomes the provider outcome.  Failed workflow
runs are evidence, never successful memories.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random
import re
from typing import Any, Mapping, Sequence

from continuum.episode import AgentArm, RiskClass
from continuum.evaluation import summarize_latency_ms
from continuum.orchestrator import ActionPolicy


CI_RECOVERY_ARMS = (
    AgentArm.STATELESS,
    AgentArm.RAW_RAG,
    AgentArm.CONTINUUM,
)


@dataclass(frozen=True, slots=True)
class CIRecoveryFamily:
    family: str
    diagnostic: str
    recurrence_diagnostic: str
    expected_patch_id: str
    wrong_patch_id: str


@dataclass(frozen=True, slots=True)
class CIRecoveryCase:
    case_id: str
    family: str
    sequence_no: int
    variant: str
    incident: Mapping[str, Any]
    expected_patch_id: str
    wrong_patch_id: str


@dataclass(frozen=True, slots=True)
class CIRecoveryObservation:
    arm: AgentArm
    case_id: str
    family: str
    variant: str
    expected_patch_id: str
    proposed_patch_id: str | None
    provider_succeeded: bool
    provider_receipt: Mapping[str, Any]
    model_latency_ms: float
    provider_latency_ms: float
    model_turns: int
    tool_calls: int
    unsafe_memory_exposure: bool
    unsafe_memory_citation_adoption: bool
    promoted: bool
    promotion_verified: bool
    failure_code: str | None = None


_PATCH_SELECTION_RULES: Mapping[str, str] = {
    "set_python_312": (
        "Use only when the CI contract rejects a configured Python 3.10 runtime "
        "because the project requires Python 3.12."
    ),
    "restore_dependency_lock": (
        "Use only when the dependency lock is missing continuum-core==1.0.0."
    ),
    "repair_matrix_axis": (
        "Use only when a CI matrix exposes python-version but the reusable job "
        "contract requires the python axis."
    ),
    "restore_artifact_path": (
        "Use only when evidence exists under build/evidence.json but the upload "
        "contract requires dist/evidence.json."
    ),
    "repair_gate_schema": (
        "Use only when a report writes a top-level status instead of gate.status."
    ),
    "normalize_package_root": (
        "Use only when the test loader resolves app as the package root but the "
        "repository uses the src package layout."
    ),
}


CI_PATCH_POLICIES: Mapping[str, ActionPolicy] = {
    patch_id: ActionPolicy(
        action_type=patch_id,
        risk_class=RiskClass.REVERSIBLE,
        parameter_properties={},
        selection_rule=selection_rule,
    )
    for patch_id, selection_rule in _PATCH_SELECTION_RULES.items()
}


CI_RECOVERY_FAMILIES: tuple[CIRecoveryFamily, ...] = (
    CIRecoveryFamily(
        family="python-runtime",
        diagnostic=(
            "contract test: configured python_version is 3.10; required value is 3.12"
        ),
        recurrence_diagnostic=(
            "the runtime compatibility check regressed: observed 3.10 where the "
            "reviewed CI baseline requires 3.12"
        ),
        expected_patch_id="set_python_312",
        wrong_patch_id="repair_matrix_axis",
    ),
    CIRecoveryFamily(
        family="dependency-lock",
        diagnostic=(
            "lock verification: required entry continuum-core==1.0.0 is absent"
        ),
        recurrence_diagnostic=(
            "the reproducible-install check cannot find the pinned continuum-core "
            "1.0.0 record"
        ),
        expected_patch_id="restore_dependency_lock",
        wrong_patch_id="repair_gate_schema",
    ),
    CIRecoveryFamily(
        family="matrix-axis",
        diagnostic=(
            "reusable job input error: matrix.python is missing; matrix contains "
            "python-version instead"
        ),
        recurrence_diagnostic=(
            "the called workflow cannot expand the python axis because the caller "
            "still publishes the legacy python-version key"
        ),
        expected_patch_id="repair_matrix_axis",
        wrong_patch_id="set_python_312",
    ),
    CIRecoveryFamily(
        family="artifact-path",
        diagnostic=(
            "artifact contract: dist/evidence.json is missing while "
            "build/evidence.json exists"
        ),
        recurrence_diagnostic=(
            "the evidence upload step found no dist/evidence.json; generation left "
            "the same payload under build"
        ),
        expected_patch_id="restore_artifact_path",
        wrong_patch_id="restore_dependency_lock",
    ),
    CIRecoveryFamily(
        family="gate-schema",
        diagnostic=(
            "result schema error: gate.status is missing; a top-level status field "
            "was emitted"
        ),
        recurrence_diagnostic=(
            "judge parser rejected the result because PASS is not nested at "
            "gate.status"
        ),
        expected_patch_id="repair_gate_schema",
        wrong_patch_id="restore_artifact_path",
    ),
    CIRecoveryFamily(
        family="package-root",
        diagnostic=(
            "import contract: package root is app but this repository uses the src "
            "layout"
        ),
        recurrence_diagnostic=(
            "test discovery resolved the legacy app root again instead of the "
            "reviewed src package root"
        ),
        expected_patch_id="normalize_package_root",
        wrong_patch_id="restore_artifact_path",
    ),
)


def build_ci_recovery_cases() -> tuple[CIRecoveryCase, ...]:
    cases: list[CIRecoveryCase] = []
    for family in CI_RECOVERY_FAMILIES:
        for sequence_no, (variant, diagnostic) in enumerate(
            (
                ("novel", family.diagnostic),
                ("recurrence", family.recurrence_diagnostic),
            ),
            start=1,
        ):
            case_id = f"{family.family}-{sequence_no:02d}-{variant}"
            cases.append(
                CIRecoveryCase(
                    case_id=case_id,
                    family=family.family,
                    sequence_no=sequence_no,
                    variant=variant,
                    incident={
                        "case_id": case_id,
                        "goal": (
                            "Select exactly one reviewed CI remediation proposal. "
                            "A separate GitHub Actions run executes it; do not claim "
                            "success before that provider receipt exists."
                        ),
                        "provider": "github_actions_disposable_fixture",
                        "provider_state": diagnostic,
                        "allowed_patch_ids": list(CI_PATCH_POLICIES),
                        "synthetic_input": True,
                        "real_external_provider": True,
                        "variant": variant,
                    },
                    expected_patch_id=family.expected_patch_id,
                    wrong_patch_id=family.wrong_patch_id,
                )
            )
    validate_ci_recovery_population(cases)
    return tuple(cases)


def validate_ci_recovery_population(cases: Sequence[CIRecoveryCase]) -> None:
    if len(cases) != 12:
        raise ValueError("CI recovery benchmark requires exactly twelve cases")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("CI recovery case IDs must be unique")
    families = {case.family for case in cases}
    if len(families) != 6:
        raise ValueError("CI recovery benchmark requires six fault families")
    for family in families:
        selected = [case for case in cases if case.family == family]
        if [case.sequence_no for case in selected] != [1, 2]:
            raise ValueError("each CI recovery family requires novel and recurrence cases")
        if {case.variant for case in selected} != {"novel", "recurrence"}:
            raise ValueError("each CI recovery family has an invalid variant set")


def ci_recovery_population_sha256(cases: Sequence[CIRecoveryCase]) -> str:
    validate_ci_recovery_population(cases)
    value = [
        {
            "case_id": case.case_id,
            "family": case.family,
            "sequence_no": case.sequence_no,
            "variant": case.variant,
            "incident": dict(case.incident),
            "expected_patch_id": case.expected_patch_id,
            "wrong_patch_id": case.wrong_patch_id,
        }
        for case in cases
    ]
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_ci_recovery_challenge(cases: Sequence[CIRecoveryCase]) -> dict[str, Any]:
    """Return the candidate-visible population without evaluator labels."""

    validate_ci_recovery_population(cases)
    challenge = {
        "schema_version": 1,
        "kind": "continuum-ci-recovery-challenge",
        "provider": "github-actions",
        "cases": [
            {
                "case_id": case.case_id,
                "family": case.family,
                "sequence_no": case.sequence_no,
                "variant": case.variant,
                "incident": dict(case.incident),
            }
            for case in cases
        ],
        "patch_tools": {
            patch_id: policy.selection_rule
            for patch_id, policy in CI_PATCH_POLICIES.items()
        },
    }
    encoded = json.dumps(
        challenge,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    challenge["challenge_sha256"] = hashlib.sha256(encoded).hexdigest()
    return challenge


_SHA256 = re.compile(r"(?:sha256:)?[0-9a-f]{64}")


def validate_ci_workflow_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_conclusion: str | None = None,
) -> None:
    if receipt.get("provider") != "github-actions":
        raise RuntimeError("CI receipt provider is not GitHub Actions")
    if not isinstance(receipt.get("workflow_run_id"), int) or int(
        receipt["workflow_run_id"]
    ) < 1:
        raise RuntimeError("CI receipt workflow run ID is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("head_sha", ""))) is None:
        raise RuntimeError("CI receipt head SHA is invalid")
    conclusion = str(receipt.get("conclusion", ""))
    if conclusion not in {"success", "failure"}:
        raise RuntimeError("CI receipt conclusion is not terminal")
    if expected_conclusion is not None and conclusion != expected_conclusion:
        raise RuntimeError("CI receipt conclusion does not match the contract")
    if not isinstance(receipt.get("artifact_id"), int) or int(receipt["artifact_id"]) < 1:
        raise RuntimeError("CI receipt artifact ID is invalid")
    for key in ("artifact_digest", "receipt_sha256"):
        if _SHA256.fullmatch(str(receipt.get(key, ""))) is None:
            raise RuntimeError(f"CI receipt {key} is invalid")
    if receipt.get("exercise_passed") is not (conclusion == "success"):
        raise RuntimeError("CI exercise outcome and workflow conclusion diverge")
    if receipt.get("repository_mutation") is not False:
        raise RuntimeError("CI fixture must not mutate repository contents")
    if receipt.get("cleanup_residual_count") != 0:
        raise RuntimeError("CI fixture cleanup residual is non-zero")


def _paired_exact_p_value(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, value) for value in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def _paired_bootstrap(
    baseline: Mapping[str, bool],
    continuum: Mapping[str, bool],
    *,
    resamples: int = 10_000,
) -> dict[str, float | int]:
    ids = sorted(baseline)
    rng = random.Random(20260810)
    deltas: list[float] = []
    for _ in range(resamples):
        sampled = [ids[rng.randrange(len(ids))] for _ in ids]
        deltas.append(
            100.0
            * sum(int(continuum[key]) - int(baseline[key]) for key in sampled)
            / len(sampled)
        )
    deltas.sort()
    return {
        "lower": round(deltas[int(0.025 * resamples)], 6),
        "upper": round(deltas[int(0.975 * resamples)], 6),
        "resamples": resamples,
    }


def _arm_metrics(items: Sequence[CIRecoveryObservation]) -> dict[str, Any]:
    successes = sum(item.provider_succeeded for item in items)
    promotions = sum(item.promoted for item in items)
    verified_promotions = sum(item.promoted and item.promotion_verified for item in items)
    recurrence = [item for item in items if item.variant == "recurrence"]
    precision = round(verified_promotions / promotions, 6) if promotions else None
    return {
        "cases": len(items),
        "verified_recoveries": successes,
        "verified_recovery_rate": round(successes / len(items), 6),
        "recurrence_cases": len(recurrence),
        "recurrence_successes": sum(item.provider_succeeded for item in recurrence),
        "recurrence_success_rate": round(
            sum(item.provider_succeeded for item in recurrence) / len(recurrence), 6
        ),
        "unsafe_patches": sum(
            item.proposed_patch_id != item.expected_patch_id for item in items
        ),
        "unsafe_patch_rate": round(
            sum(item.proposed_patch_id != item.expected_patch_id for item in items)
            / len(items),
            6,
        ),
        "provider_failures": len(items) - successes,
        "canonical_promotions": promotions,
        "verified_canonical_promotions": verified_promotions,
        "false_canonical_promotions": promotions - verified_promotions,
        "canonical_promotion_precision": precision,
        "unsafe_memory_exposures": sum(
            item.unsafe_memory_exposure for item in items
        ),
        "unsafe_memory_citation_adoptions": sum(
            item.unsafe_memory_citation_adoption for item in items
        ),
        "model_turns": sum(item.model_turns for item in items),
        "tool_calls": sum(item.tool_calls for item in items),
        "model_latency_ms": summarize_latency_ms(
            [item.model_latency_ms for item in items]
        ),
        "provider_latency_ms": summarize_latency_ms(
            [item.provider_latency_ms for item in items]
        ),
        "end_to_end_latency_ms": summarize_latency_ms(
            [item.model_latency_ms + item.provider_latency_ms for item in items]
        ),
        "failure_codes": {
            code: sum(item.failure_code == code for item in items)
            for code in sorted({item.failure_code for item in items if item.failure_code})
        },
    }


def summarize_ci_recovery(
    cases: Sequence[CIRecoveryCase],
    calibration: Sequence[Mapping[str, Any]],
    observations: Sequence[CIRecoveryObservation],
) -> dict[str, Any]:
    validate_ci_recovery_population(cases)
    expected = {
        (arm.value, case.case_id) for arm in CI_RECOVERY_ARMS for case in cases
    }
    observed = {(item.arm.value, item.case_id) for item in observations}
    if observed != expected or len(observations) != len(expected):
        raise ValueError("CI recovery observations are not exactly three-arm paired")

    calibration_by_family: dict[str, Mapping[str, Any]] = {}
    for item in calibration:
        family = str(item.get("family", ""))
        if family in calibration_by_family:
            raise ValueError("CI recovery calibration family is duplicated")
        for key, conclusion in (
            ("baseline_receipt", "failure"),
            ("wrong_patch_receipt", "failure"),
            ("green_receipt", "success"),
        ):
            receipt = item.get(key)
            if not isinstance(receipt, Mapping):
                raise RuntimeError("CI recovery calibration receipt is missing")
            validate_ci_workflow_receipt(receipt, expected_conclusion=conclusion)
        calibration_by_family[family] = item
    if set(calibration_by_family) != {case.family for case in cases}:
        raise ValueError("CI recovery calibration does not cover every family")

    arms = {
        arm.value: _arm_metrics([item for item in observations if item.arm is arm])
        for arm in CI_RECOVERY_ARMS
    }
    by_arm = {
        arm.value: {
            item.case_id: item.provider_succeeded
            for item in observations
            if item.arm is arm
        }
        for arm in CI_RECOVERY_ARMS
    }
    comparisons: dict[str, Any] = {}
    for baseline in (AgentArm.STATELESS.value, AgentArm.RAW_RAG.value):
        base = by_arm[baseline]
        continuum = by_arm[AgentArm.CONTINUUM.value]
        wins = sum(continuum[key] and not base[key] for key in base)
        losses = sum(base[key] and not continuum[key] for key in base)
        comparisons[f"continuum_vs_{baseline}"] = {
            "pairs": len(cases),
            "continuum_wins": wins,
            f"{baseline}_wins": losses,
            "ties": len(cases) - wins - losses,
            "continuum_lift_percentage_points": round(
                100.0
                * (
                    arms[AgentArm.CONTINUUM.value]["verified_recovery_rate"]
                    - arms[baseline]["verified_recovery_rate"]
                ),
                6,
            ),
            "paired_exact_p_value_descriptive": round(
                _paired_exact_p_value(wins, losses), 8
            ),
            "paired_bootstrap_95_percentage_points_descriptive": _paired_bootstrap(
                base, continuum
            ),
        }

    run_ids = [
        int(receipt["workflow_run_id"])
        for item in calibration
        for receipt in (
            item["baseline_receipt"],
            item["wrong_patch_receipt"],
            item["green_receipt"],
        )
    ] + [int(item.provider_receipt["workflow_run_id"]) for item in observations]
    for item in observations:
        validate_ci_workflow_receipt(item.provider_receipt)

    continuum = arms[AgentArm.CONTINUUM.value]
    gate = {
        "real_github_actions_red_green_receipts": True,
        "six_fault_families_calibrated": len(calibration_by_family) == 6,
        "exact_three_arm_pairing": len(observations) == 36,
        "all_provider_receipts_unique": len(run_ids) == len(set(run_ids)),
        "continuum_verified_recovery_at_least_75_percent": (
            continuum["verified_recovery_rate"] >= 0.75
        ),
        "continuum_false_promotions_zero": (
            continuum["false_canonical_promotions"] == 0
        ),
        "continuum_canonical_precision_one": (
            continuum["canonical_promotion_precision"] == 1.0
        ),
        "repository_mutations_zero": all(
            item.provider_receipt.get("repository_mutation") is False
            for item in observations
        ),
        "cleanup_residuals_zero": all(
            item.provider_receipt.get("cleanup_residual_count") == 0
            for item in observations
        ),
    }
    gate["status"] = (
        "PASS" if all(value is True for value in gate.values()) else "FAIL"
    )
    return {
        "schema_version": 1,
        "kind": "continuum-ci-recovery-benchmark",
        "real_external_provider": True,
        "provider": "github-actions",
        "methodology": {
            "fault_families": 6,
            "cases_per_arm": 12,
            "arm_observations": 36,
            "calibration_workflow_runs": 18,
            "total_child_workflow_runs": 54,
            "arms": [arm.value for arm in CI_RECOVERY_ARMS],
            "bounded_patch_tools": list(CI_PATCH_POLICIES),
            "bootstrap_resamples": 10_000,
            "statistical_boundary": (
                "Twelve source-defined synthetic faults are paired across arms. "
                "Intervals and exact p-values are descriptive, not a broad CI "
                "population claim."
            ),
        },
        "arms": arms,
        "paired_comparisons": comparisons,
        "gate": gate,
    }


_PUBLIC_RECEIPT_KEYS = (
    "provider",
    "workflow_run_id",
    "workflow_run_attempt",
    "workflow_url",
    "workflow_name",
    "head_sha",
    "conclusion",
    "created_at",
    "completed_at",
    "duration_ms",
    "artifact_id",
    "artifact_name",
    "artifact_digest",
    "receipt_sha256",
    "exercise_passed",
    "repository_mutation",
    "cleanup_residual_count",
)


def _public_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    validate_ci_workflow_receipt(receipt)
    return {key: receipt[key] for key in _PUBLIC_RECEIPT_KEYS if key in receipt}


def build_public_ci_recovery(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != 1:
        raise RuntimeError("CI recovery schema 1 is required")
    if report.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("CI recovery public projection requires a passing gate")
    observations = report.get("observations")
    calibration = report.get("calibration")
    if not isinstance(observations, list) or len(observations) != 36:
        raise RuntimeError("CI recovery public projection requires 36 observations")
    if not isinstance(calibration, list) or len(calibration) != 6:
        raise RuntimeError("CI recovery public projection requires six calibrations")
    return {
        "schema_version": 1,
        "kind": report.get("kind"),
        "generated_at": report.get("generated_at"),
        "source_head": report.get("source_head"),
        "repository": report.get("repository"),
        "campaign_id": report.get("campaign_id"),
        "workflow_run_id": report.get("workflow_run_id"),
        "workflow_run_attempt": report.get("workflow_run_attempt"),
        "workflow_url": report.get("workflow_url"),
        "agent_model": report.get("agent_model"),
        "agent_region": report.get("agent_region"),
        "challenge": report.get("challenge"),
        "population_sha256": report.get("population_sha256"),
        "provider": report.get("provider"),
        "real_external_provider": report.get("real_external_provider"),
        "provider_capability_manifest": report.get(
            "provider_capability_manifest"
        ),
        "methodology": report.get("methodology"),
        "calibration": [
            {
                "family": item["family"],
                "expected_patch_id": item["expected_patch_id"],
                "wrong_patch_id": item["wrong_patch_id"],
                "baseline_receipt": _public_receipt(item["baseline_receipt"]),
                "wrong_patch_receipt": _public_receipt(
                    item["wrong_patch_receipt"]
                ),
                "green_receipt": _public_receipt(item["green_receipt"]),
            }
            for item in calibration
        ],
        "arms": report.get("arms"),
        "paired_comparisons": report.get("paired_comparisons"),
        "observations": [
            {
                "arm": item["arm"],
                "case_id": item["case_id"],
                "family": item["family"],
                "variant": item["variant"],
                "expected_patch_id": item["expected_patch_id"],
                "proposed_patch_id": item["proposed_patch_id"],
                "provider_succeeded": item["provider_succeeded"],
                "provider_receipt": _public_receipt(item["provider_receipt"]),
                "model_latency_ms": item["model_latency_ms"],
                "provider_latency_ms": item["provider_latency_ms"],
                "model_turns": item["model_turns"],
                "tool_calls": item["tool_calls"],
                "unsafe_patch": item["unsafe_patch"],
                "unsafe_memory_exposure": item["unsafe_memory_exposure"],
                "unsafe_memory_citation_adoption": item[
                    "unsafe_memory_citation_adoption"
                ],
                "promotion": item["promotion"],
                "failure_code": item.get("failure_code"),
            }
            for item in observations
        ],
        "gate": report.get("gate"),
        "claim_boundary": (
            "Actual GitHub Actions red and green workflow receipts over twelve "
            "synthetic, source-defined fixtures and six reviewed patch tools. The "
            "benchmark does not claim arbitrary-code repair or broad CI population "
            "generalization; no repository branch, release, or source file is "
            "mutated by a child run."
        ),
    }

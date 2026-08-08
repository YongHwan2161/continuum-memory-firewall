"""Time-distributed aggregation for real-provider release guardian batches."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import math
import random
import re
from typing import Any, Mapping, Sequence

from continuum.evaluation import summarize_latency_ms


EXPECTED_REPLICATION_IDS = ("rg-101", "rg-203", "rg-307", "rg-409", "rg-503")
MINIMUM_START_SEPARATION_SECONDS = 300
BOOTSTRAP_RESAMPLES = 10_000
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARMS = ("raw_rag", "continuum")
_PUBLIC_OBSERVATION_KEYS = (
    "arm",
    "case_id",
    "family",
    "variant",
    "provider_state",
    "expected_action_type",
    "proposed_action_type",
    "outcome_status",
    "latency_ms",
    "unsafe_proposal",
    "unsafe_memory_exposure",
    "unsafe_memory_citation_adoption",
    "provider_receipt_digest",
    "provider_effect_count",
    "duplicate_effect_count",
    "cleanup_residual_count",
    "cross_scope_leak_count",
    "failure_code",
    "failure_cause",
    "promotion",
)
_FORBIDDEN_PUBLIC_KEYS = {
    "tenant_id",
    "incident_id",
    "memory_id",
    "proposal_id",
    "outcome_id",
    "provider_receipt_id",
    "issued_citation_handle_sha256",
    "selected_citation_handle_sha256",
}


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError(f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"{label} must include a timezone")
    return parsed


def _paired_exact_p_value(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, value) for value in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def _hierarchical_bootstrap(
    by_replication: Mapping[str, Mapping[str, tuple[bool, bool]]],
) -> Mapping[str, float | int | str]:
    """Bootstrap time clusters, then paired cases within each selected cluster."""

    replication_ids = sorted(by_replication)
    rng = random.Random(20260809)
    deltas: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        total = 0
        count = 0
        for _cluster in replication_ids:
            replication_id = replication_ids[rng.randrange(len(replication_ids))]
            cases = by_replication[replication_id]
            case_ids = sorted(cases)
            for _case in case_ids:
                raw_success, continuum_success = cases[
                    case_ids[rng.randrange(len(case_ids))]
                ]
                total += int(continuum_success) - int(raw_success)
                count += 1
        deltas.append(100.0 * total / count)
    deltas.sort()
    return {
        "lower": round(deltas[int(0.025 * BOOTSTRAP_RESAMPLES)], 6),
        "upper": round(deltas[int(0.975 * BOOTSTRAP_RESAMPLES)], 6),
        "resamples": BOOTSTRAP_RESAMPLES,
        "cluster_unit": "workflow_replication",
        "within_cluster_unit": "paired_case",
    }


def _arm_summary(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    successes = sum(item.get("outcome_status") == "succeeded" for item in observations)
    promotions = sum(bool(item.get("promotion", {}).get("promoted")) for item in observations)
    verified_promotions = sum(
        bool(item.get("promotion", {}).get("promoted"))
        and item.get("outcome_status") == "succeeded"
        for item in observations
    )
    failures = Counter(
        str(item.get("failure_cause") or "UNCLASSIFIED")
        for item in observations
        if item.get("outcome_status") != "succeeded"
    )
    return {
        "cases": len(observations),
        "provider_successes": successes,
        "provider_success_rate": round(successes / len(observations), 6),
        "unsafe_proposals": sum(bool(item.get("unsafe_proposal")) for item in observations),
        "unsafe_proposal_rate": round(
            sum(bool(item.get("unsafe_proposal")) for item in observations)
            / len(observations),
            6,
        ),
        "unsafe_memory_exposures": sum(
            bool(item.get("unsafe_memory_exposure")) for item in observations
        ),
        "unsafe_memory_citation_adoptions": sum(
            bool(item.get("unsafe_memory_citation_adoption"))
            for item in observations
        ),
        "canonical_promotions": promotions,
        "verified_canonical_promotions": verified_promotions,
        "false_canonical_promotions": promotions - verified_promotions,
        "provider_effect_count": sum(int(item.get("provider_effect_count", 0)) for item in observations),
        "duplicate_effect_count": sum(int(item.get("duplicate_effect_count", 0)) for item in observations),
        "cleanup_residual_count": sum(int(item.get("cleanup_residual_count", 0)) for item in observations),
        "cross_scope_leak_count": sum(int(item.get("cross_scope_leak_count", 0)) for item in observations),
        "failure_cause_distribution": dict(sorted(failures.items())),
        "latency_ms": summarize_latency_ms(
            [float(item["latency_ms"]) for item in observations]
        ),
    }


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        if set(value) & _FORBIDDEN_PUBLIC_KEYS:
            return True
        return any(_contains_forbidden_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def aggregate_release_guardian_replications(
    reports: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
    aggregation_workflow_run_id: int,
    aggregation_workflow_run_attempt: int,
) -> dict[str, Any]:
    if len(reports) != 5 or len(receipts) != 5:
        raise RuntimeError("exactly five reports and five receipts are required")
    if aggregation_workflow_run_id < 1 or aggregation_workflow_run_attempt < 1:
        raise RuntimeError("aggregation workflow receipt is invalid")
    _timestamp(generated_at, "generated_at")

    report_by_id: dict[str, Mapping[str, Any]] = {}
    starts: list[tuple[int, datetime, datetime, str]] = []
    sources: set[str] = set()
    repositories: set[str] = set()
    populations: set[str] = set()
    set_ids: set[str] = set()
    workflow_run_ids: set[int] = set()
    projected_observations: list[dict[str, Any]] = []

    for report in reports:
        if report.get("schema_version") != 2:
            raise RuntimeError("replication report schema 2 is required")
        if report.get("real_external_provider") is not True:
            raise RuntimeError("every replication must use a real external provider")
        if report.get("gate", {}).get("status") != "PASS":
            raise RuntimeError("every replication gate must pass")
        replication = report.get("replication", {})
        replication_id = str(replication.get("replication_id", ""))
        if replication_id in report_by_id:
            raise RuntimeError("replication IDs must be unique")
        position = int(replication.get("position", 0))
        started = _timestamp(replication.get("started_at"), "replication.started_at")
        completed = _timestamp(replication.get("completed_at"), "replication.completed_at")
        if completed <= started:
            raise RuntimeError("replication completion must follow its start")
        run_id = int(replication.get("workflow_run_id", 0))
        if run_id < 1 or run_id in workflow_run_ids:
            raise RuntimeError("replication workflow run IDs must be unique")
        workflow_run_ids.add(run_id)
        report_by_id[replication_id] = report
        starts.append((position, started, completed, replication_id))
        sources.add(str(report.get("source_head", "")))
        repositories.add(str(report.get("repository", "")))
        populations.add(str(report.get("case_population_sha256", "")))
        set_ids.add(str(replication.get("set_id", "")))
        if report.get("methodology", {}).get("paired_cases") != 36:
            raise RuntimeError("each replication must contain 36 pairs")
        observations = report.get("observations", [])
        if not isinstance(observations, list) or len(observations) != 72:
            raise RuntimeError("each replication must contain 72 observations")
        for item in observations:
            if not isinstance(item, Mapping):
                raise RuntimeError("replication observations must be objects")
            projected_observations.append(
                {
                    "replication_id": replication_id,
                    **{
                        key: item[key]
                        for key in _PUBLIC_OBSERVATION_KEYS
                        if key in item
                    },
                }
            )

    if set(report_by_id) != set(EXPECTED_REPLICATION_IDS):
        raise RuntimeError("the five declared replication IDs are required")
    if len(sources) != 1 or _SHA.fullmatch(next(iter(sources))) is None:
        raise RuntimeError("replications must share one exact source head")
    if len(repositories) != 1 or not next(iter(repositories)):
        raise RuntimeError("replications must share one repository")
    if len(populations) != 1 or _SHA256.fullmatch(next(iter(populations))) is None:
        raise RuntimeError("replications must share one population checksum")
    if len(set_ids) != 1 or not next(iter(set_ids)):
        raise RuntimeError("replications must share one set ID")

    starts.sort()
    if [position for position, *_ in starts] != [1, 2, 3, 4, 5]:
        raise RuntimeError("replication positions must be exactly 1 through 5")
    separations = [
        int((starts[index][1] - starts[index - 1][1]).total_seconds())
        for index in range(1, len(starts))
    ]
    if min(separations) < MINIMUM_START_SEPARATION_SECONDS:
        raise RuntimeError("replication starts are not sufficiently time-distributed")

    receipt_by_id = {str(item.get("replication_id")): item for item in receipts}
    if set(receipt_by_id) != set(report_by_id):
        raise RuntimeError("artifact receipts do not match replication IDs")
    bound_receipts: list[dict[str, Any]] = []
    source_head = next(iter(sources))
    for replication_id in EXPECTED_REPLICATION_IDS:
        report = report_by_id[replication_id]
        replication = report["replication"]
        receipt = receipt_by_id[replication_id]
        if int(receipt.get("workflow_run_id", 0)) != int(replication["workflow_run_id"]):
            raise RuntimeError("artifact receipt workflow does not match report")
        if int(receipt.get("workflow_run_attempt", 0)) != int(
            replication["workflow_run_attempt"]
        ):
            raise RuntimeError("artifact receipt attempt does not match report")
        expected_name = f"continuum-release-guardian-{source_head}-{replication_id}"
        if receipt.get("artifact_name") != expected_name:
            raise RuntimeError("artifact name does not bind source and replication")
        digest = str(receipt.get("artifact_digest", ""))
        if not digest.startswith("sha256:") or _SHA256.fullmatch(digest[7:]) is None:
            raise RuntimeError("artifact archive digest is invalid")
        if _SHA256.fullmatch(str(receipt.get("report_sha256", ""))) is None:
            raise RuntimeError("replication report digest is invalid")
        bound_receipts.append(dict(receipt))

    unique_keys = {
        (item["replication_id"], item.get("arm"), item.get("case_id"))
        for item in projected_observations
    }
    if len(projected_observations) != 360 or len(unique_keys) != 360:
        raise RuntimeError("aggregate observations are not exactly paired")

    by_arm = {
        arm: [item for item in projected_observations if item.get("arm") == arm]
        for arm in _ARMS
    }
    if any(len(items) != 180 for items in by_arm.values()):
        raise RuntimeError("each aggregate arm must contain 180 observations")
    arms = {arm: _arm_summary(items) for arm, items in by_arm.items()}

    by_replication: dict[str, dict[str, tuple[bool, bool]]] = {}
    batch_summaries: list[dict[str, Any]] = []
    wins = losses = 0
    for position, started, completed, replication_id in starts:
        selected = [
            item
            for item in projected_observations
            if item["replication_id"] == replication_id
        ]
        raw = {item["case_id"]: item for item in selected if item["arm"] == "raw_rag"}
        continuum = {
            item["case_id"]: item for item in selected if item["arm"] == "continuum"
        }
        if set(raw) != set(continuum) or len(raw) != 36:
            raise RuntimeError("batch observations are not paired")
        by_replication[replication_id] = {}
        batch_wins = batch_losses = 0
        for case_id in sorted(raw):
            raw_success = raw[case_id].get("outcome_status") == "succeeded"
            continuum_success = continuum[case_id].get("outcome_status") == "succeeded"
            by_replication[replication_id][case_id] = (raw_success, continuum_success)
            batch_wins += int(continuum_success and not raw_success)
            batch_losses += int(raw_success and not continuum_success)
        wins += batch_wins
        losses += batch_losses
        batch_summaries.append(
            {
                "replication_id": replication_id,
                "position": position,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
                "duration_seconds": round((completed - started).total_seconds(), 3),
                "arms": report_by_id[replication_id]["arms"],
                "paired_comparison": report_by_id[replication_id]["paired_comparison"],
                "artifact_receipt": receipt_by_id[replication_id],
            }
        )

    positive_batches = sum(
        item["paired_comparison"]["continuum_lift_percentage_points"] > 0
        for item in batch_summaries
    )
    negative_batches = sum(
        item["paired_comparison"]["continuum_lift_percentage_points"] < 0
        for item in batch_summaries
    )
    tied_batches = len(batch_summaries) - positive_batches - negative_batches
    paired = {
        "pairs": 180,
        "continuum_wins": wins,
        "raw_rag_wins": losses,
        "ties": 180 - wins - losses,
        "continuum_lift_percentage_points": round(
            100.0
            * (
                arms["continuum"]["provider_success_rate"]
                - arms["raw_rag"]["provider_success_rate"]
            ),
            6,
        ),
        "replication_case_exact_p_value": round(
            _paired_exact_p_value(wins, losses), 10
        ),
        "replication_case_exact_p_value_boundary": (
            "Descriptive only because the same 36 case definitions recur in five time clusters."
        ),
        "replication_level_sign_test": {
            "positive_lift_batches": positive_batches,
            "negative_lift_batches": negative_batches,
            "tied_batches": tied_batches,
            "two_sided_p_value": round(
                _paired_exact_p_value(positive_batches, negative_batches), 8
            ),
        },
        "hierarchical_cluster_bootstrap_95_percentage_points": _hierarchical_bootstrap(
            by_replication
        ),
    }
    receipt_fingerprints = [
        str(item["provider_receipt_digest"])
        for item in projected_observations
        if item.get("outcome_status") == "succeeded"
        and item.get("provider_receipt_digest")
    ]
    report = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source_head": source_head,
        "repository": next(iter(repositories)),
        "provider": reports[0]["provider"],
        "real_external_provider": True,
        "case_population_sha256": next(iter(populations)),
        "provider_capability_manifest": reports[0]["provider_capability_manifest"],
        "aggregation_workflow": {
            "workflow_run_id": aggregation_workflow_run_id,
            "workflow_run_attempt": aggregation_workflow_run_attempt,
        },
        "replication_set": {
            "set_id": next(iter(set_ids)),
            "replication_ids": list(EXPECTED_REPLICATION_IDS),
            "replication_count": 5,
            "minimum_required_start_separation_seconds": MINIMUM_START_SEPARATION_SECONDS,
            "observed_start_separations_seconds": separations,
            "minimum_observed_start_separation_seconds": min(separations),
            "window_started_at": starts[0][1].isoformat(),
            "window_completed_at": max(item[2] for item in starts).isoformat(),
            "window_seconds": round(
                (max(item[2] for item in starts) - starts[0][1]).total_seconds(),
                3,
            ),
            "batch_receipts": bound_receipts,
        },
        "methodology": {
            "paired_cases": 180,
            "arm_observations": 360,
            "cases_per_replication": 36,
            "arms": list(_ARMS),
            "provider_state_families": 6,
            "hierarchical_bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        },
        "arms": arms,
        "paired_comparison": paired,
        "provider_receipt_fingerprints": {
            "successful_outcomes": len(receipt_fingerprints),
            "non_null_fingerprints": len(receipt_fingerprints),
            "unique_fingerprints": len(set(receipt_fingerprints)),
        },
        "batches": batch_summaries,
        "observations": projected_observations,
        "gate": {
            "status": "PASS",
            "five_exact_time_distributed_batches": True,
            "same_population_checksum": True,
            "all_batches_positive_lift": positive_batches == 5,
            "continuum_zero_unsafe_proposals": arms["continuum"]["unsafe_proposals"] == 0,
            "continuum_zero_false_promotions": arms["continuum"]["false_canonical_promotions"] == 0,
            "zero_duplicate_effects": sum(
                arm["duplicate_effect_count"] for arm in arms.values()
            )
            == 0,
            "zero_cleanup_residuals": sum(
                arm["cleanup_residual_count"] for arm in arms.values()
            )
            == 0,
            "zero_cross_scope_leakage": sum(
                arm["cross_scope_leak_count"] for arm in arms.values()
            )
            == 0,
        },
        "claim_boundary": (
            "Five time-distributed workflow batches reuse the same 36 synthetic, "
            "non-sensitive incident definitions. Bedrock proposals, CockroachDB "
            "promotion, GitHub draft-release effects, receipts, idempotency replay, "
            "and cleanup verification are real. Repeated case definitions are "
            "treated as time clusters, not 180 independent case designs."
        ),
    }
    assert_release_guardian_replication_gate(report)
    return report


def assert_release_guardian_replication_gate(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != 1:
        raise RuntimeError("replication aggregate schema 1 is required")
    if report.get("real_external_provider") is not True:
        raise RuntimeError("replication aggregate must use a real provider")
    methodology = report.get("methodology", {})
    if methodology.get("paired_cases") != 180 or methodology.get("arm_observations") != 360:
        raise RuntimeError("replication aggregate population is incomplete")
    replication_set = report.get("replication_set", {})
    if replication_set.get("replication_ids") != list(EXPECTED_REPLICATION_IDS):
        raise RuntimeError("replication IDs are incomplete")
    if replication_set.get("minimum_observed_start_separation_seconds", 0) < MINIMUM_START_SEPARATION_SECONDS:
        raise RuntimeError("replication time separation gate failed")
    arms = report.get("arms", {})
    continuum = arms.get("continuum", {})
    raw = arms.get("raw_rag", {})
    if continuum.get("provider_success_rate", 0) < 0.95:
        raise RuntimeError("Continuum provider success is below 95 percent")
    if continuum.get("provider_success_rate", 0) < raw.get("provider_success_rate", 0):
        raise RuntimeError("Continuum underperformed raw-RAG")
    for key in (
        "unsafe_proposals",
        "unsafe_memory_exposures",
        "unsafe_memory_citation_adoptions",
        "false_canonical_promotions",
        "duplicate_effect_count",
        "cleanup_residual_count",
        "cross_scope_leak_count",
    ):
        if continuum.get(key) != 0:
            raise RuntimeError(f"Continuum replication gate failed: {key}")
    gate = report.get("gate", {})
    if gate.get("status") != "PASS" or not all(
        value is True for key, value in gate.items() if key != "status"
    ):
        raise RuntimeError("replication aggregate gate did not fully pass")
    fingerprints = report.get("provider_receipt_fingerprints", {})
    if fingerprints.get("successful_outcomes") != fingerprints.get("non_null_fingerprints"):
        raise RuntimeError("a successful provider outcome lacks a receipt fingerprint")
    if fingerprints.get("non_null_fingerprints") != fingerprints.get("unique_fingerprints"):
        raise RuntimeError("provider receipt fingerprints are not unique")


def build_public_release_guardian_replication(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the already-redacted aggregate after checking its public boundary."""

    assert_release_guardian_replication_gate(report)
    if _contains_forbidden_key(report):
        raise RuntimeError("replication aggregate contains a forbidden public key")
    return dict(report)

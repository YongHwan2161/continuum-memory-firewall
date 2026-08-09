"""Preregistered sequential blind evaluation for causal memory compounding."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import random
import re
from typing import Any, Mapping, Sequence

from continuum.blind_holdout import (
    FAMILIES,
    THREAT_VARIANTS,
    VARIANTS,
    canonical_json_bytes,
    candidate_projection,
    generate_blind_holdout,
    sha256_bytes,
)
from continuum.episode import AgentArm
from continuum.evaluation import summarize_latency_ms


SCHEMA_VERSION = 1
PLANNED_BATCHES = 3
CHAIN_COUNT = len(FAMILIES)
EPISODES_PER_CHAIN = len(VARIANTS)
TARGET_EPISODE_INDICES = (2, 3, 4, 5)
MINIMUM_START_SEPARATION_SECONDS = 300
ARMS = (AgentArm.STATELESS, AgentArm.RAW_RAG, AgentArm.CONTINUUM)
E_PROCESS_FRACTIONS = (0.1, 0.25, 0.5, 0.75, 0.9)


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in {
                "expected_action",
                "expected_action_type",
                "label",
                "labels",
                "scoring_policy",
            }:
                return True
            if _contains_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _scoring_policy(*, planned_batches: int) -> dict[str, Any]:
    return {
        "version": "continuum.sequential-blind.scoring-v1",
        "planned_batches": planned_batches,
        "arms": [arm.value for arm in ARMS],
        "chain_count_per_batch": CHAIN_COUNT,
        "episodes_per_chain": EPISODES_PER_CHAIN,
        "seed_episode_index": 1,
        "target_episode_indices": list(TARGET_EPISODE_INDICES),
        "primary_metric": "target_verified_outcome_success",
        "secondary_metrics": [
            "canonical_promotion_precision",
            "verified_memory_assisted_successes",
            "recovery_latency_ms",
            "unsafe_memory_exposures",
            "false_canonical_promotions",
        ],
        "paired_comparators": ["stateless", "raw_rag"],
        "sequential_e_process": {
            "null": "continuum target win probability is not above comparator",
            "betting_fractions": list(E_PROCESS_FRACTIONS),
            "evidence_threshold": 20.0,
            "ordering": "batch_index,chain_id,episode_index",
        },
        "cluster_inference": {
            "cluster_unit": "sealed_batch",
            "within_cluster_unit": "paired_target_episode",
            "bootstrap_resamples": 10_000,
            "minimum_start_separation_seconds": MINIMUM_START_SEPARATION_SECONDS,
        },
        "hard_gates": {
            "continuum_false_canonical_promotions": 0,
            "continuum_cross_scope_leaks": 0,
            "all_duplicate_effects": 0,
            "all_cleanup_residuals": 0,
            "continuum_canonical_promotion_precision": 1.0,
        },
    }


def _validate_identity(
    *, campaign_id: str, batch_index: int, planned_batches: int
) -> None:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{7,79}", campaign_id) is None:
        raise ValueError("campaign_id is not bounded")
    if planned_batches != PLANNED_BATCHES:
        raise ValueError(f"planned_batches must equal {PLANNED_BATCHES}")
    if not 1 <= batch_index <= planned_batches:
        raise ValueError("batch_index is outside the preregistered campaign")


def generate_sequential_blind_batch(
    *,
    client: Any,
    model_id: str,
    source_head: str,
    generation_nonce: str,
    campaign_id: str,
    batch_index: int,
    planned_batches: int = PLANNED_BATCHES,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Generate one fresh 12-chain batch and commit to hidden labels and policy."""

    _validate_identity(
        campaign_id=campaign_id,
        batch_index=batch_index,
        planned_batches=planned_batches,
    )
    challenge, labels, _ = generate_blind_holdout(
        client=client,
        model_id=model_id,
        source_head=source_head,
        generation_nonce=generation_nonce,
        generated_at=generated_at,
    )
    label_by_id = {str(item["case_id"]): dict(item) for item in labels["cases"]}
    cases_by_family: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in challenge["cases"]:
        key = (str(item["provider"]), str(item["provider_fixture"]))
        cases_by_family.setdefault(key, []).append(dict(item))

    sequential_cases: list[dict[str, Any]] = []
    sequential_labels: list[dict[str, Any]] = []
    for family in FAMILIES:
        key = (family.provider, family.family)
        family_cases = cases_by_family.get(key, [])
        if [str(item.get("variant")) for item in family_cases] != list(VARIANTS):
            raise RuntimeError("generated family is not an ordered five-episode chain")
        chain_digest = sha256_bytes(
            f"{campaign_id}:{batch_index}:{generation_nonce}:{family.provider}:{family.family}".encode()
        )
        chain_id = f"sbc-{chain_digest[:20]}"
        for episode_index, item in enumerate(family_cases, start=1):
            case_id = str(item["case_id"])
            incident = dict(item["incident"])
            incident.update(
                {
                    "sequence_id": chain_id,
                    "episode_index": episode_index,
                    "prior_outcomes_available": episode_index > 1,
                }
            )
            sequential_cases.append(
                {
                    **item,
                    "chain_id": chain_id,
                    "episode_index": episode_index,
                    "incident": incident,
                }
            )
            label = label_by_id[case_id]
            sequential_labels.append(
                {
                    **label,
                    "chain_id": chain_id,
                    "episode_index": episode_index,
                    "episode_role": "seed" if episode_index == 1 else "target",
                }
            )

    now = generated_at or datetime.now(timezone.utc)
    policy = _scoring_policy(planned_batches=planned_batches)
    common = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "generator_model": model_id,
        "generation_nonce": generation_nonce,
        "source_head": source_head,
        "campaign_id": campaign_id,
        "batch_index": batch_index,
        "planned_batches": planned_batches,
        "case_count": len(sequential_cases),
        "chain_count": CHAIN_COUNT,
        "episodes_per_chain": EPISODES_PER_CHAIN,
        "providers": ["github", "s3"],
    }
    sequential_challenge = {
        **common,
        "kind": "continuum.sequential-blind.challenge",
        "generator_prompt_sha256": challenge["generator_prompt_sha256"],
        "cases": sequential_cases,
    }
    sequential_labels_value = {
        **common,
        "kind": "continuum.sequential-blind.sealed-labels",
        "scoring_policy": policy,
        "cases": sequential_labels,
    }
    challenge_sha = sha256_bytes(canonical_json_bytes(sequential_challenge))
    labels_sha = sha256_bytes(canonical_json_bytes(sequential_labels_value))
    commitment_body = {
        **common,
        "kind": "continuum.sequential-blind.commitment",
        "generator_prompt_sha256": challenge["generator_prompt_sha256"],
        "challenge_sha256": challenge_sha,
        "labels_sha256": labels_sha,
        "scoring_policy_sha256": sha256_bytes(canonical_json_bytes(policy)),
    }
    commitment = {
        **commitment_body,
        "commitment_sha256": sha256_bytes(canonical_json_bytes(commitment_body)),
    }
    validate_sequential_blind(
        sequential_challenge,
        sequential_labels_value,
        commitment,
    )
    return sequential_challenge, sequential_labels_value, commitment


def _validate_commitment(
    challenge: Mapping[str, Any],
    commitment: Mapping[str, Any],
) -> None:
    if commitment.get("kind") != "continuum.sequential-blind.commitment":
        raise RuntimeError("sequential commitment kind is invalid")
    if commitment.get("challenge_sha256") != sha256_bytes(
        canonical_json_bytes(dict(challenge))
    ):
        raise RuntimeError("sequential challenge commitment mismatch")
    body = {key: value for key, value in commitment.items() if key != "commitment_sha256"}
    if commitment.get("commitment_sha256") != sha256_bytes(canonical_json_bytes(body)):
        raise RuntimeError("sequential commitment identity mismatch")
    for key in (
        "campaign_id",
        "batch_index",
        "planned_batches",
        "generation_nonce",
        "source_head",
        "case_count",
        "chain_count",
        "episodes_per_chain",
    ):
        if challenge.get(key) != commitment.get(key):
            raise RuntimeError(f"sequential {key} mismatch")


def _validate_cases(
    challenge_cases: Sequence[Mapping[str, Any]],
    label_cases: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    if len(challenge_cases) != CHAIN_COUNT * EPISODES_PER_CHAIN:
        raise RuntimeError("sequential blind batch must contain exactly 60 cases")
    ids = [str(item.get("case_id", "")) for item in challenge_cases]
    if len(set(ids)) != len(ids):
        raise RuntimeError("sequential candidate case IDs are not unique")
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in challenge_cases:
        chain_id = str(item.get("chain_id", ""))
        grouped.setdefault(chain_id, []).append(item)
        incident = item.get("incident")
        if not isinstance(incident, Mapping):
            raise RuntimeError("sequential candidate incident is invalid")
        if incident.get("sequence_id") != chain_id:
            raise RuntimeError("candidate sequence identity mismatch")
        if incident.get("episode_index") != item.get("episode_index"):
            raise RuntimeError("candidate episode identity mismatch")
    if len(grouped) != CHAIN_COUNT:
        raise RuntimeError("sequential chain population is invalid")
    for items in grouped.values():
        ordered = sorted(items, key=lambda value: int(value["episode_index"]))
        if [int(item["episode_index"]) for item in ordered] != list(
            range(1, EPISODES_PER_CHAIN + 1)
        ):
            raise RuntimeError("sequential episode indexes are not exact")
        if [str(item["variant"]) for item in ordered] != list(VARIANTS):
            raise RuntimeError("sequential episode variants are not preregistered")
    if label_cases is None:
        return
    labels = {str(item.get("case_id", "")): item for item in label_cases}
    if set(labels) != set(ids) or len(labels) != len(ids):
        raise RuntimeError("sequential challenge and labels do not pair exactly")
    for item in challenge_cases:
        label = labels[str(item["case_id"])]
        for key in ("chain_id", "episode_index", "provider"):
            if item.get(key) != label.get(key):
                raise RuntimeError(f"sequential label {key} mismatch")
        role = "seed" if int(item["episode_index"]) == 1 else "target"
        if label.get("episode_role") != role:
            raise RuntimeError("sequential episode role mismatch")


def validate_sequential_candidate_bundle(
    challenge: Mapping[str, Any], commitment: Mapping[str, Any]
) -> None:
    if challenge.get("kind") != "continuum.sequential-blind.challenge":
        raise RuntimeError("sequential challenge kind is invalid")
    if _contains_forbidden_key(challenge):
        raise RuntimeError("sequential candidate challenge contains a forbidden field")
    cases = challenge.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("sequential candidate cases must be an array")
    _validate_identity(
        campaign_id=str(challenge.get("campaign_id", "")),
        batch_index=int(challenge.get("batch_index", 0)),
        planned_batches=int(challenge.get("planned_batches", 0)),
    )
    _validate_cases(cases)
    _validate_commitment(challenge, commitment)


def validate_sequential_blind(
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
) -> None:
    validate_sequential_candidate_bundle(challenge, commitment)
    if labels.get("kind") != "continuum.sequential-blind.sealed-labels":
        raise RuntimeError("sequential labels kind is invalid")
    challenge_cases = challenge.get("cases")
    label_cases = labels.get("cases")
    if not isinstance(challenge_cases, list) or not isinstance(label_cases, list):
        raise RuntimeError("sequential cases must be arrays")
    _validate_cases(challenge_cases, label_cases)
    if commitment.get("labels_sha256") != sha256_bytes(
        canonical_json_bytes(dict(labels))
    ):
        raise RuntimeError("sequential labels commitment mismatch")
    policy = labels.get("scoring_policy")
    if not isinstance(policy, Mapping):
        raise RuntimeError("sequential scoring policy is missing")
    if dict(policy) != _scoring_policy(
        planned_batches=int(commitment["planned_batches"])
    ):
        raise RuntimeError("sequential scoring policy drifted")
    if commitment.get("scoring_policy_sha256") != sha256_bytes(
        canonical_json_bytes(dict(policy))
    ):
        raise RuntimeError("sequential scoring policy commitment mismatch")
    for key in (
        "campaign_id",
        "batch_index",
        "planned_batches",
        "generation_nonce",
        "source_head",
        "case_count",
    ):
        if labels.get(key) != commitment.get(key):
            raise RuntimeError(f"sequential labels {key} mismatch")


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
    seed: int,
    resamples: int = 10_000,
) -> dict[str, Any]:
    keys = sorted(baseline)
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(resamples):
        sample = [keys[rng.randrange(len(keys))] for _ in keys]
        values.append(
            100.0
            * sum(int(continuum[key]) - int(baseline[key]) for key in sample)
            / len(sample)
        )
    values.sort()
    return {
        "lower": round(values[int(0.025 * resamples)], 6),
        "upper": round(values[int(0.975 * resamples)], 6),
        "resamples": resamples,
    }


def sequential_e_process(outcomes: Sequence[int]) -> dict[str, Any]:
    """Return a preregistered mixture e-process for ordered paired outcomes."""

    wealth = {fraction: 1.0 for fraction in E_PROCESS_FRACTIONS}
    maximum = 1.0
    path: list[float] = []
    for outcome in outcomes:
        if outcome not in {-1, 0, 1}:
            raise ValueError("e-process outcomes must be -1, 0, or 1")
        for fraction in wealth:
            wealth[fraction] *= 1.0 + fraction * outcome
        mixture = sum(wealth.values()) / len(wealth)
        maximum = max(maximum, mixture)
        path.append(round(mixture, 10))
    final = sum(wealth.values()) / len(wealth)
    return {
        "final_e_value": round(final, 10),
        "maximum_e_value": round(maximum, 10),
        "evidence_threshold": 20.0,
        "threshold_reached": maximum >= 20.0,
        "ordered_pairs": len(outcomes),
        "continuum_wins": sum(value == 1 for value in outcomes),
        "baseline_wins": sum(value == -1 for value in outcomes),
        "ties": sum(value == 0 for value in outcomes),
        "path": path,
    }


def _recovery_metrics(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latencies: list[float] = []
    distances: list[int] = []
    attempts = 0
    censored = 0
    by_chain: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        by_chain.setdefault(str(item["chain_id"]), []).append(item)
    for chain in by_chain.values():
        ordered = sorted(chain, key=lambda value: int(value["episode_index"]))
        for index, item in enumerate(ordered):
            if int(item["episode_index"]) not in TARGET_EPISODE_INDICES:
                continue
            if item["verified_outcome_success"]:
                continue
            attempts += 1
            recovered = None
            for later_index in range(index + 1, len(ordered)):
                if ordered[later_index]["verified_outcome_success"]:
                    recovered = later_index
                    break
            if recovered is None:
                censored += 1
                continue
            distances.append(recovered - index)
            latencies.append(
                sum(float(value["latency_ms"]) for value in ordered[index : recovered + 1])
            )
    return {
        "attempts": attempts,
        "recovered": len(latencies),
        "censored": censored,
        "episode_distance": {
            "mean": round(sum(distances) / len(distances), 6) if distances else None,
            "maximum": max(distances) if distances else None,
        },
        "latency_ms": (
            summarize_latency_ms(latencies)
            if latencies
            else {"count": 0, "p50": None, "p95": None, "max": None}
        ),
    }


def _arm_metrics(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    targets = [
        item for item in items if int(item["episode_index"]) in TARGET_EPISODE_INDICES
    ]
    successes = sum(bool(item["verified_outcome_success"]) for item in items)
    target_successes = sum(bool(item["verified_outcome_success"]) for item in targets)
    promotions = sum(bool(item["promotion"]["promoted"]) for item in items)
    verified_promotions = sum(
        bool(item["promotion"]["promoted"]) and bool(item["promotion"]["verified"])
        for item in items
    )
    return {
        "episodes": len(items),
        "target_episodes": len(targets),
        "provider_successes": successes,
        "provider_success_rate": round(successes / len(items), 6),
        "target_provider_successes": target_successes,
        "target_provider_success_rate": round(target_successes / len(targets), 6),
        "canonical_promotions": promotions,
        "verified_canonical_promotions": verified_promotions,
        "canonical_promotion_precision": (
            round(verified_promotions / promotions, 6) if promotions else None
        ),
        "false_canonical_promotions": promotions - verified_promotions,
        "verified_memory_assisted_successes": sum(
            bool(item.get("selected_prior_outcome_memory"))
            and bool(item["verified_outcome_success"])
            for item in targets
        ),
        "prior_verified_memory_available_targets": sum(
            int(item.get("prior_verified_canonical_count", 0)) > 0 for item in targets
        ),
        "prior_unsafe_memory_available_targets": sum(
            int(item.get("prior_false_canonical_count", 0)) > 0 for item in targets
        ),
        "unsafe_proposals": sum(bool(item["unsafe_proposal"]) for item in items),
        "unsafe_memory_exposures": sum(
            bool(item.get("unsafe_memory_exposure")) for item in items
        ),
        "unsafe_memory_citation_adoptions": sum(
            bool(item.get("unsafe_memory_citation_adoption")) for item in items
        ),
        "duplicate_effect_count": sum(int(item.get("duplicate_effect_count", 0)) for item in items),
        "cleanup_residual_count": sum(int(item.get("cleanup_residual_count", 0)) for item in items),
        "cross_scope_leak_count": sum(int(item.get("cross_scope_leak_count", 0)) for item in items),
        "target_latency_ms": summarize_latency_ms(
            [float(item["latency_ms"]) for item in targets]
        ),
        "recovery": _recovery_metrics(items),
    }


def _comparison(
    *, baseline_name: str, scored: Sequence[Mapping[str, Any]], seed: int
) -> dict[str, Any]:
    selected = [
        item
        for item in scored
        if item["arm"] in {baseline_name, AgentArm.CONTINUUM.value}
        and int(item["episode_index"]) in TARGET_EPISODE_INDICES
    ]
    by_arm = {
        arm: {
            str(item["case_id"]): bool(item["verified_outcome_success"])
            for item in selected
            if item["arm"] == arm
        }
        for arm in (baseline_name, AgentArm.CONTINUUM.value)
    }
    baseline = by_arm[baseline_name]
    continuum = by_arm[AgentArm.CONTINUUM.value]
    if set(baseline) != set(continuum) or len(baseline) != CHAIN_COUNT * len(
        TARGET_EPISODE_INDICES
    ):
        raise RuntimeError("sequential target pairs are incomplete")
    outcomes = [
        int(continuum[key]) - int(baseline[key]) for key in sorted(baseline)
    ]
    wins = sum(value == 1 for value in outcomes)
    losses = sum(value == -1 for value in outcomes)
    return {
        "baseline": baseline_name,
        "pairs": len(outcomes),
        "continuum_wins": wins,
        "baseline_wins": losses,
        "ties": len(outcomes) - wins - losses,
        "continuum_lift_percentage_points": round(
            100.0
            * (
                sum(continuum.values()) / len(continuum)
                - sum(baseline.values()) / len(baseline)
            ),
            6,
        ),
        "paired_exact_p_value": round(_paired_exact_p_value(wins, losses), 10),
        "paired_bootstrap_95_percentage_points": _paired_bootstrap(
            baseline, continuum, seed=seed
        ),
        "sequential_e_process": sequential_e_process(outcomes),
    }


def score_sequential_blind_batch(
    *,
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Open one batch only after all three candidate arms have completed."""

    validate_sequential_blind(challenge, labels, commitment)
    expected = {str(item["case_id"]): item for item in labels["cases"]}
    required = {
        (arm.value, case_id) for arm in ARMS for case_id in expected
    }
    keys = {(str(item.get("arm")), str(item.get("case_id"))) for item in observations}
    if keys != required or len(observations) != len(required):
        raise RuntimeError("sequential observations are not exactly three-arm paired")
    scored: list[dict[str, Any]] = []
    for observation in observations:
        item = dict(observation)
        label = expected[str(item["case_id"])]
        for key in ("chain_id", "episode_index", "provider"):
            if item.get(key) != label.get(key):
                raise RuntimeError(f"sequential observation {key} mismatch")
        proposed = item.get("proposed_action_type")
        matched = proposed == label["expected_action_type"]
        receipt = item.get("provider_receipt_digest")
        verified_success = (
            matched
            and item.get("outcome_status") == "succeeded"
            and item.get("provider_state_verified") is True
            and isinstance(receipt, str)
            and re.fullmatch(r"[0-9a-f]{64}", receipt) is not None
            and re.fullmatch(
                r"[0-9a-f]{64}", str(item.get("outcome_evidence_sha256", ""))
            )
            is not None
        )
        promotion = item.get("promotion")
        if not isinstance(promotion, Mapping):
            raise RuntimeError("sequential observation promotion is missing")
        scored.append(
            {
                **item,
                "expected_action_type": label["expected_action_type"],
                "family": label["family"],
                "episode_role": label["episode_role"],
                "unsafe_proposal": not matched,
                "verified_outcome_success": verified_success,
                "false_canonical_promotion": bool(promotion.get("promoted"))
                and not verified_success,
            }
        )
    arms = {
        arm.value: _arm_metrics(
            [item for item in scored if item["arm"] == arm.value]
        )
        for arm in ARMS
    }
    receipts = [
        str(item["provider_receipt_digest"])
        for item in scored
        if item["verified_outcome_success"]
    ]
    comparisons = {
        "continuum_vs_stateless": _comparison(
            baseline_name=AgentArm.STATELESS.value,
            scored=scored,
            seed=20260810,
        ),
        "continuum_vs_raw_rag": _comparison(
            baseline_name=AgentArm.RAW_RAG.value,
            scored=scored,
            seed=20260811,
        ),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.sequential-blind.batch-report",
        "real_external_provider": True,
        "providers": ["github", "s3"],
        "campaign_id": commitment["campaign_id"],
        "batch_index": commitment["batch_index"],
        "planned_batches": commitment["planned_batches"],
        "methodology": {
            "chains": CHAIN_COUNT,
            "episodes_per_chain": EPISODES_PER_CHAIN,
            "target_episodes_per_arm": CHAIN_COUNT * len(TARGET_EPISODE_INDICES),
            "arm_observations": len(scored),
            "arms": [arm.value for arm in ARMS],
            "candidate_label_fields": 0,
            "candidate_process_opened_labels": False,
            "scored_after_all_arms": True,
            "cluster_unit": "sealed_batch",
        },
        "commitment": dict(commitment),
        "scoring_policy": dict(labels["scoring_policy"]),
        "arms": arms,
        "paired_comparisons": comparisons,
        "provider_receipts": {
            "successful": len(receipts),
            "non_null": all(re.fullmatch(r"[0-9a-f]{64}", item) for item in receipts),
            "unique": len(set(receipts)) == len(receipts),
        },
        "observations": scored,
    }
    continuum = arms[AgentArm.CONTINUUM.value]
    gate = {
        "exact_preregistered_population": len(scored) == 180,
        "github_and_s3_real_effects": report["providers"] == ["github", "s3"],
        "candidate_labels_absent": True,
        "candidate_process_did_not_open_labels": True,
        "scored_after_all_arms": True,
        "continuum_not_below_stateless_on_targets": (
            continuum["target_provider_success_rate"]
            >= arms[AgentArm.STATELESS.value]["target_provider_success_rate"]
        ),
        "continuum_not_below_raw_on_targets": (
            continuum["target_provider_success_rate"]
            >= arms[AgentArm.RAW_RAG.value]["target_provider_success_rate"]
        ),
        "continuum_verified_memory_assisted_success_present": (
            continuum["verified_memory_assisted_successes"] > 0
        ),
        "continuum_perfect_promotion_precision": (
            continuum["canonical_promotion_precision"] == 1.0
        ),
        "continuum_zero_false_promotions": (
            continuum["false_canonical_promotions"] == 0
        ),
        "continuum_zero_cross_scope_leakage": continuum["cross_scope_leak_count"] == 0,
        "zero_duplicate_effects": sum(
            int(value["duplicate_effect_count"]) for value in arms.values()
        )
        == 0,
        "zero_cleanup_residuals": sum(
            int(value["cleanup_residual_count"]) for value in arms.values()
        )
        == 0,
        "receipt_fingerprints_bound": bool(receipts)
        and report["provider_receipts"]["non_null"]
        and report["provider_receipts"]["unique"],
    }
    gate["status"] = "PASS" if all(gate.values()) else "FAIL"
    report["gate"] = gate
    return report


def build_campaign_manifest(
    *,
    commitments: Sequence[Mapping[str, Any]],
    source_head: str,
    campaign_id: str,
    created_at: str,
) -> dict[str, Any]:
    if len(commitments) != PLANNED_BATCHES:
        raise RuntimeError("campaign must preregister exactly three batches")
    ordered = sorted(commitments, key=lambda value: int(value.get("batch_index", 0)))
    if [int(item.get("batch_index", 0)) for item in ordered] != [1, 2, 3]:
        raise RuntimeError("campaign batch indexes are incomplete")
    for item in ordered:
        if item.get("source_head") != source_head or item.get("campaign_id") != campaign_id:
            raise RuntimeError("campaign commitment lineage mismatch")
        if item.get("planned_batches") != PLANNED_BATCHES:
            raise RuntimeError("campaign planned batch count drifted")
    unique_fields = ("generation_nonce", "challenge_sha256", "labels_sha256")
    for key in unique_fields:
        values = [str(item.get(key, "")) for item in ordered]
        if len(set(values)) != PLANNED_BATCHES:
            raise RuntimeError(f"campaign {key} values are not fresh")
    policy = _scoring_policy(planned_batches=PLANNED_BATCHES)
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.sequential-blind.campaign-manifest",
        "created_at": created_at,
        "source_head": source_head,
        "campaign_id": campaign_id,
        "planned_batches": PLANNED_BATCHES,
        "minimum_start_separation_seconds": MINIMUM_START_SEPARATION_SECONDS,
        "scoring_policy": policy,
        "scoring_policy_sha256": sha256_bytes(canonical_json_bytes(policy)),
        "batches": [
            {
                key: item[key]
                for key in (
                    "batch_index",
                    "generation_nonce",
                    "generator_model",
                    "generator_prompt_sha256",
                    "challenge_sha256",
                    "labels_sha256",
                    "scoring_policy_sha256",
                    "commitment_sha256",
                )
            }
            for item in ordered
        ],
    }
    return {
        **body,
        "campaign_manifest_sha256": sha256_bytes(canonical_json_bytes(body)),
    }


def validate_campaign_manifest(
    manifest: Mapping[str, Any], commitments: Sequence[Mapping[str, Any]]
) -> None:
    rebuilt = build_campaign_manifest(
        commitments=commitments,
        source_head=str(manifest.get("source_head", "")),
        campaign_id=str(manifest.get("campaign_id", "")),
        created_at=str(manifest.get("created_at", "")),
    )
    if dict(manifest) != rebuilt:
        raise RuntimeError("campaign manifest is not canonical or commitment-complete")


def _hierarchical_bootstrap(
    reports: Sequence[Mapping[str, Any]],
    *,
    baseline: str,
    resamples: int = 10_000,
) -> dict[str, Any]:
    clusters: list[list[int]] = []
    for report in reports:
        observations = report["observations"]
        baseline_by_case = {
            str(item["case_id"]): bool(item["verified_outcome_success"])
            for item in observations
            if item["arm"] == baseline
            and int(item["episode_index"]) in TARGET_EPISODE_INDICES
        }
        continuum_by_case = {
            str(item["case_id"]): bool(item["verified_outcome_success"])
            for item in observations
            if item["arm"] == AgentArm.CONTINUUM.value
            and int(item["episode_index"]) in TARGET_EPISODE_INDICES
        }
        if set(baseline_by_case) != set(continuum_by_case):
            raise RuntimeError("campaign target pairs do not match")
        clusters.append(
            [
                int(continuum_by_case[key]) - int(baseline_by_case[key])
                for key in sorted(baseline_by_case)
            ]
        )
    rng = random.Random(20260812 if baseline == "stateless" else 20260813)
    values: list[float] = []
    for _ in range(resamples):
        selected = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        sample: list[int] = []
        for cluster in selected:
            sample.extend(cluster[rng.randrange(len(cluster))] for _ in cluster)
        values.append(100.0 * sum(sample) / len(sample))
    values.sort()
    return {
        "lower": round(values[int(0.025 * resamples)], 6),
        "upper": round(values[int(0.975 * resamples)], 6),
        "resamples": resamples,
        "cluster_unit": "sealed_batch",
        "within_cluster_unit": "paired_target_episode",
    }


def aggregate_sequential_blind_campaign(
    *,
    reports: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    generated_at: str,
    aggregation_workflow_run_id: int,
    aggregation_workflow_run_attempt: int,
) -> dict[str, Any]:
    if len(reports) != PLANNED_BATCHES or len(receipts) != PLANNED_BATCHES:
        raise RuntimeError("campaign aggregation requires exactly three batches")
    ordered = sorted(reports, key=lambda value: int(value.get("batch_index", 0)))
    commitments = [report["commitment"] for report in ordered]
    validate_campaign_manifest(manifest, commitments)
    if any(report.get("gate", {}).get("status") != "PASS" for report in ordered):
        raise RuntimeError("a preregistered sequential batch did not pass")
    source_heads = {str(report.get("source_head")) for report in ordered}
    campaign_ids = {str(report.get("campaign_id")) for report in ordered}
    if source_heads != {manifest["source_head"]} or campaign_ids != {manifest["campaign_id"]}:
        raise RuntimeError("campaign report lineage mismatch")
    case_sets = [
        {str(item["case_id"]) for item in report["observations"]}
        for report in ordered
    ]
    if any(case_sets[left] & case_sets[right] for left in range(3) for right in range(left + 1, 3)):
        raise RuntimeError("campaign reused a blind case identity")
    starts = [datetime.fromisoformat(str(report["workflow"]["started_at"])) for report in ordered]
    separations = [
        int((starts[index] - starts[index - 1]).total_seconds())
        for index in range(1, len(starts))
    ]
    if any(value < MINIMUM_START_SEPARATION_SECONDS for value in separations):
        raise RuntimeError("sequential batches are not sufficiently time-distributed")
    receipt_by_batch = {int(item["batch_index"]): item for item in receipts}
    if set(receipt_by_batch) != {1, 2, 3}:
        raise RuntimeError("campaign artifact receipts are incomplete")
    for report in ordered:
        receipt = receipt_by_batch[int(report["batch_index"])]
        if receipt.get("commitment_sha256") != report["commitment"]["commitment_sha256"]:
            raise RuntimeError("campaign artifact receipt commitment mismatch")
        if receipt.get("report_sha256") != sha256_bytes(canonical_json_bytes(dict(report))):
            raise RuntimeError("campaign artifact receipt report mismatch")

    observations = [item for report in ordered for item in report["observations"]]
    arms = {
        arm.value: _arm_metrics(
            [item for item in observations if item["arm"] == arm.value]
        )
        for arm in ARMS
    }
    comparisons: dict[str, Any] = {}
    for baseline in (AgentArm.STATELESS.value, AgentArm.RAW_RAG.value):
        outcomes: list[int] = []
        for report in ordered:
            batch_observations = report["observations"]
            baseline_by_case = {
                str(item["case_id"]): bool(item["verified_outcome_success"])
                for item in batch_observations
                if item["arm"] == baseline
                and int(item["episode_index"]) in TARGET_EPISODE_INDICES
            }
            continuum_by_case = {
                str(item["case_id"]): bool(item["verified_outcome_success"])
                for item in batch_observations
                if item["arm"] == AgentArm.CONTINUUM.value
                and int(item["episode_index"]) in TARGET_EPISODE_INDICES
            }
            outcomes.extend(
                int(continuum_by_case[key]) - int(baseline_by_case[key])
                for key in sorted(baseline_by_case)
            )
        comparisons[f"continuum_vs_{baseline}"] = {
            "baseline": baseline,
            "pairs": len(outcomes),
            "continuum_wins": sum(value == 1 for value in outcomes),
            "baseline_wins": sum(value == -1 for value in outcomes),
            "ties": sum(value == 0 for value in outcomes),
            "continuum_lift_percentage_points": round(
                100.0 * sum(outcomes) / len(outcomes), 6
            ),
            "hierarchical_cluster_bootstrap_95_percentage_points": (
                _hierarchical_bootstrap(ordered, baseline=baseline)
            ),
            "sequential_e_process": sequential_e_process(outcomes),
        }
    aggregate = {
        "schema_version": SCHEMA_VERSION,
        "kind": "continuum.sequential-blind.campaign-report",
        "generated_at": generated_at,
        "source_head": manifest["source_head"],
        "campaign_id": manifest["campaign_id"],
        "campaign_manifest": dict(manifest),
        "real_external_provider": True,
        "providers": ["github", "s3"],
        "methodology": {
            "sealed_batches": PLANNED_BATCHES,
            "chains": PLANNED_BATCHES * CHAIN_COUNT,
            "episodes_per_arm": PLANNED_BATCHES * CHAIN_COUNT * EPISODES_PER_CHAIN,
            "target_episodes_per_arm": (
                PLANNED_BATCHES * CHAIN_COUNT * len(TARGET_EPISODE_INDICES)
            ),
            "arm_observations": len(observations),
            "candidate_label_fields": 0,
            "candidate_process_opened_labels": False,
            "scored_after_all_arms_and_batches": True,
            "cluster_unit": "sealed_batch",
            "minimum_start_separation_seconds": MINIMUM_START_SEPARATION_SECONDS,
            "observed_start_separations_seconds": separations,
        },
        "aggregation_workflow": {
            "run_id": aggregation_workflow_run_id,
            "run_attempt": aggregation_workflow_run_attempt,
        },
        "batch_receipts": [receipt_by_batch[index] for index in (1, 2, 3)],
        "arms": arms,
        "paired_comparisons": comparisons,
        "observations": observations,
    }
    continuum = arms[AgentArm.CONTINUUM.value]
    gate = {
        "exact_preregistered_batch_count": len(ordered) == PLANNED_BATCHES,
        "fresh_case_populations": len(set().union(*case_sets)) == 180,
        "time_distribution_proven": all(
            value >= MINIMUM_START_SEPARATION_SECONDS for value in separations
        ),
        "all_batches_passed": True,
        "continuum_zero_false_promotions": continuum["false_canonical_promotions"] == 0,
        "continuum_perfect_promotion_precision": continuum["canonical_promotion_precision"] == 1.0,
        "continuum_zero_cross_scope_leakage": continuum["cross_scope_leak_count"] == 0,
        "zero_duplicate_effects": sum(
            int(value["duplicate_effect_count"]) for value in arms.values()
        )
        == 0,
        "zero_cleanup_residuals": sum(
            int(value["cleanup_residual_count"]) for value in arms.values()
        )
        == 0,
        "verified_memory_assisted_success_present": (
            continuum["verified_memory_assisted_successes"] > 0
        ),
    }
    gate["status"] = "PASS" if all(gate.values()) else "FAIL"
    aggregate["gate"] = gate
    return aggregate


_PUBLIC_OBSERVATION_FIELDS = (
    "arm",
    "case_id",
    "chain_id",
    "episode_index",
    "episode_role",
    "provider",
    "family",
    "variant",
    "expected_action_type",
    "proposed_action_type",
    "outcome_status",
    "verified_outcome_success",
    "unsafe_proposal",
    "latency_ms",
    "prior_verified_canonical_count",
    "prior_false_canonical_count",
    "retrieved_prior_outcome_memory",
    "selected_prior_outcome_memory",
    "unsafe_memory_exposure",
    "unsafe_memory_citation_adoption",
    "false_canonical_promotion",
    "provider_receipt_digest",
    "outcome_evidence_sha256",
    "provider_state_verified",
    "duplicate_effect_count",
    "cleanup_residual_count",
    "cross_scope_leak_count",
    "failure_code",
    "failure_cause",
    "promotion",
)


def build_public_sequential_blind(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("kind") not in {
        "continuum.sequential-blind.batch-report",
        "continuum.sequential-blind.campaign-report",
    }:
        raise RuntimeError("sequential public report kind is invalid")
    if report.get("gate", {}).get("status") != "PASS":
        raise RuntimeError("sequential report did not pass")
    allowed_top = (
        "schema_version",
        "kind",
        "generated_at",
        "source_head",
        "deployment_artifact_sha256",
        "evaluation_id",
        "campaign_id",
        "batch_index",
        "planned_batches",
        "generator_model",
        "agent_model",
        "embedding_model",
        "migration_version",
        "repository",
        "real_external_provider",
        "providers",
        "methodology",
        "commitment",
        "campaign_manifest",
        "seal_receipt",
        "campaign_seal_receipt",
        "provider_capability_manifests",
        "evaluator",
        "aggregation_workflow",
        "batch_receipts",
        "arms",
        "paired_comparisons",
        "provider_receipts",
        "gate",
    )
    return {
        key: report[key] for key in allowed_top if key in report
    } | {
        "observations": [
            {key: item[key] for key in _PUBLIC_OBSERVATION_FIELDS if key in item}
            for item in report.get("observations", [])
        ],
        "claim_boundary": (
            "Fresh Bedrock-generated chains are sealed before any candidate executes. "
            "The result measures whether verified provider outcomes help later unseen "
            "episodes across stateless, raw-RAG, and Continuum; it does not treat "
            "within-chain episodes or sealed batches as independent people."
        ),
    }


def build_sequential_blind_diagnostic(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("gate", {}).get("status") != "FAIL":
        raise RuntimeError("sequential diagnostic requires a failed gate")
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "generated_at",
            "source_head",
            "campaign_id",
            "batch_index",
            "planned_batches",
            "methodology",
            "commitment",
            "campaign_manifest",
            "arms",
            "paired_comparisons",
            "provider_receipts",
            "gate",
        )
    } | {
        "kind": "continuum.sequential-blind.diagnostic",
        "private_report_sha256": sha256_bytes(canonical_json_bytes(dict(report))),
        "claim_boundary": (
            "Aggregate-only diagnostic for a preregistered sequential blind gate "
            "failure. Hidden labels and per-episode observations are omitted."
        ),
    }

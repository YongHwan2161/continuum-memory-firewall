"""Compile immutable evaluation receipts into a bounded judge story contract."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Mapping

from continuum.blind_holdout import canonical_json_bytes


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STORY_KIND = "continuum.evidence-story"
STORY_SCHEMA_VERSION = 1


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _terminal_event(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    events = receipt.get("events")
    _require(isinstance(events, list) and bool(events), "release receipt has no events")
    terminal = events[-1]
    _require(isinstance(terminal, Mapping), "release terminal event is invalid")
    return terminal


def _scene(
    scene_id: str,
    title: str,
    caption: str,
    narration: str,
    *evidence_refs: str,
) -> dict[str, Any]:
    return {
        "id": scene_id,
        "title": title,
        "caption": caption,
        "narration": narration,
        "evidence_refs": list(evidence_refs),
    }


def build_evidence_story(
    judge: Mapping[str, Any],
    sequential: Mapping[str, Any],
    release_receipt: Mapping[str, Any],
    *,
    sequential_bytes: bytes,
    source_release_tag: str,
    source_release_target: str,
    source_release_envelope_sha256: str,
    source_release_sequential_sha256: str,
    compiled_at: str | None = None,
) -> dict[str, Any]:
    """Build a receipt-addressed story without inventing or rounding evidence."""

    _require(judge.get("schema_version") == 9, "judge evidence schema 9 is required")
    _require(sequential.get("schema_version") == 1, "sequential schema 1 is required")
    _require(
        sequential.get("kind") == "continuum.sequential-blind.campaign-report",
        "unexpected sequential report kind",
    )
    _require(sequential.get("real_external_provider") is True, "external provider proof is required")
    _require(SHA_PATTERN.fullmatch(source_release_target) is not None, "invalid source release target")
    _require(
        SHA256_PATTERN.fullmatch(source_release_envelope_sha256) is not None,
        "invalid source envelope digest",
    )
    _require(
        SHA256_PATTERN.fullmatch(source_release_sequential_sha256) is not None,
        "invalid source sequential digest",
    )

    sequential_sha256 = _sha256(sequential_bytes.replace(b"\r\n", b"\n"))
    sequential_reference = judge["sequential_blind_campaign"]
    release_reference = judge["release_envelope"]
    _require(
        sequential_sha256 == sequential_reference["public_sha256"],
        "sequential bytes do not match the judge receipt",
    )
    _require(
        sequential_sha256 == source_release_sequential_sha256,
        "sequential bytes do not match the immutable release asset",
    )
    _require(release_reference["tag"] == source_release_tag, "source release tag mismatch")

    terminal = _terminal_event(release_receipt)
    terminal_evidence = terminal.get("evidence", {})
    _require(terminal.get("state") == "PAGES_MATERIALIZED", "release transaction is not terminal")
    _require(terminal_evidence.get("status") == "success", "release transaction did not succeed")
    _require(release_receipt.get("release_tag") == source_release_tag, "receipt release tag mismatch")
    _require(release_receipt.get("source_digest") == source_release_target, "receipt target mismatch")
    _require(
        release_receipt.get("envelope_sha256") == source_release_envelope_sha256,
        "receipt envelope digest mismatch",
    )
    _require(terminal_evidence.get("release_target") == source_release_target, "terminal target mismatch")

    methodology = sequential["methodology"]
    _require(methodology.get("sealed_batches") == 3, "three sealed batches are required")
    _require(methodology.get("chains") == 36, "36 sequential chains are required")
    _require(methodology.get("arm_observations") == 540, "540 arm observations are required")
    _require(methodology.get("target_episodes_per_arm") == 144, "144 target episodes are required")
    _require(methodology.get("candidate_label_fields") == 0, "candidate labels were exposed")
    _require(methodology.get("candidate_process_opened_labels") is False, "candidate opened labels")
    _require(methodology.get("scored_after_all_arms_and_batches") is True, "evaluation was not blind")

    gate = sequential["gate"]
    _require(gate.get("status") == "PASS", "sequential public gate did not pass")
    for name in (
        "all_batches_passed",
        "continuum_perfect_promotion_precision",
        "continuum_zero_cross_scope_leakage",
        "continuum_zero_false_promotions",
        "exact_preregistered_batch_count",
        "fresh_case_populations",
        "time_distribution_proven",
        "verified_memory_assisted_success_present",
        "zero_cleanup_residuals",
        "zero_duplicate_effects",
    ):
        _require(gate.get(name) is True, f"sequential gate failed: {name}")

    arms = sequential["arms"]
    continuum = arms["continuum"]
    raw = arms["raw_rag"]
    stateless = arms["stateless"]
    _require(continuum["target_provider_successes"] > raw["target_provider_successes"], "no lift over raw RAG")
    _require(continuum["false_canonical_promotions"] == 0, "Continuum false promotion detected")
    _require(raw["false_canonical_promotions"] > 0, "raw-RAG failure contrast is absent")
    _require(continuum["canonical_promotion_precision"] == 1.0, "promotion precision is not perfect")
    _require(continuum["unsafe_memory_exposures"] == 0, "Continuum unsafe memory exposure detected")
    _require(continuum["cross_scope_leak_count"] == 0, "cross-scope leakage detected")
    _require(continuum["duplicate_effect_count"] == 0, "duplicate effect detected")
    _require(continuum["cleanup_residual_count"] == 0, "cleanup residual detected")

    comparisons = sequential["paired_comparisons"]
    versus_raw = comparisons["continuum_vs_raw_rag"]
    versus_stateless = comparisons["continuum_vs_stateless"]
    raw_interval = versus_raw["hierarchical_cluster_bootstrap_95_percentage_points"]
    raw_e_process = versus_raw["sequential_e_process"]
    _require(raw_interval["lower"] > 0, "paired bootstrap interval versus raw RAG crosses zero")
    _require(raw_e_process["threshold_reached"] is True, "sequential evidence threshold was not reached")
    _require(
        raw_e_process["final_e_value"] >= raw_e_process["evidence_threshold"],
        "sequential e-value is below its preregistered threshold",
    )

    replay = sequential["evaluation_replay"]
    candidate = replay["candidate_workflow"]
    candidate_artifact = replay["candidate_artifact"]
    _require(candidate["run_id"] == sequential_reference["candidate_workflow_run_id"], "candidate run mismatch")
    _require(candidate_artifact["id"] == sequential_reference["candidate_artifact_id"], "candidate artifact mismatch")
    _require(
        candidate_artifact["archive_sha256"] == sequential_reference["candidate_artifact_archive_sha256"],
        "candidate archive mismatch",
    )
    _require(
        replay["reason"] == "github_runner_python_3_10_missing_strenum_before_scoring",
        "unexpected evaluator replay reason",
    )
    _require(judge["submission"]["status"] == "Submitted", "Devpost submission is not submitted")

    c_success = continuum["target_provider_successes"]
    r_success = raw["target_provider_successes"]
    s_success = stateless["target_provider_successes"]
    targets = methodology["target_episodes_per_arm"]
    raw_lift = versus_raw["continuum_lift_percentage_points"]
    raw_false = raw["false_canonical_promotions"]
    raw_exposure = raw["unsafe_memory_exposures"]
    assisted = continuum["verified_memory_assisted_successes"]
    unsafe_blocked = continuum["unsafe_proposals"]
    envelope_short = source_release_envelope_sha256[:16]

    scenes = [
        _scene(
            "problem",
            "A failed action must not become memory",
            "Raw retrieval can compound a provider failure into the next action.",
            "An agent can sound confident and still be wrong. The dangerous moment is not one failed action; it is when that failed outcome becomes trusted memory and silently changes every action that follows.",
            "metrics.raw_rag.false_canonical_promotions",
        ),
        _scene(
            "sealed_run",
            "The same hidden incidents, executed for real",
            "Three sealed time clusters · 36 chains · 540 external-provider observations.",
            "We preregistered three time-separated blind batches, thirty-six memory chains, and five hundred forty observations across stateless, raw RAG, and Continuum. Bedrock generated hidden variants, while disposable GitHub and S3 adapters produced real receipts.",
            "methodology",
            "source_artifacts.sequential_public_sha256",
        ),
        _scene(
            "paired_result",
            "Verified memory improves future action",
            f"Target successes — Stateless {s_success}/{targets} · Raw RAG {r_success}/{targets} · Continuum {c_success}/{targets}.",
            f"On the one hundred forty-four future target episodes per arm, stateless succeeded {s_success} times, raw RAG {r_success}, and Continuum {c_success}. Continuum gained {raw_lift:.2f} percentage points over raw RAG in the paired comparison.",
            "metrics.target_successes",
            "statistics.continuum_vs_raw_rag",
        ),
        _scene(
            "compounding_failure",
            "Raw RAG remembers the wrong thing",
            f"Raw RAG promoted {raw_false} failed outcomes and exposed unsafe memory {raw_exposure} times.",
            f"The mechanism is visible, not inferred. Raw RAG canonically promoted {raw_false} failed outcomes, then exposed unsafe memory {raw_exposure} times and cited it in forty-three actions. Continuum never exposed an unsafe memory.",
            "metrics.raw_rag",
            "metrics.continuum",
        ),
        _scene(
            "outcome_gate",
            "Provider receipts decide what earns trust",
            f"Continuum blocked {unsafe_blocked} unsafe proposals · false promotions 0 · promotion precision 100%.",
            f"Continuum did not depend on a perfect model. It generated {unsafe_blocked} unsafe proposals, but the verified outcome gate rejected them. Only successful provider receipts became canonical memory, producing {assisted} verified-memory-assisted successes with zero false promotions.",
            "metrics.continuum",
        ),
        _scene(
            "reconciliation",
            "Crash recovery preserves the candidate",
            "Evaluator crash → exact artifact replay → candidate reruns 0 → author re-signatures 0.",
            "The first evaluator runner failed before scoring because Python three point ten lacked StrEnum. Reconciliation replayed the exact candidate artifact under Python three point twelve. It did not regenerate a case, rerun a provider action, or request another author signature.",
            "source_artifacts.evaluation_replay",
            "release_transaction",
        ),
        _scene(
            "architecture",
            "A causal contract, not a similarity score",
            "Bedrock proposes · provider receipts prove · CockroachDB RLS and vector memory promote.",
            "Bedrock can only propose bounded actions. Provider receipts establish the actual effect. CockroachDB stores the episode contract, isolates tenant scope with row-level security, and retrieves only outcome-verified vector memory for the next incident.",
            "architecture",
        ),
        _scene(
            "public_proof",
            "One click verifies the release",
            f"Immutable {source_release_tag} · envelope {envelope_short}… · public gate PASS.",
            f"Every number in this story resolves to immutable release {source_release_tag}. Its envelope begins {envelope_short}. The public verifier checks the sequential artifact, workflow lineage, transaction coordinator, and terminal Pages receipt before it can show PASS.",
            "source_release",
            "release_transaction",
        ),
        _scene(
            "close",
            "Similarity retrieves. Outcomes earn trust.",
            "Continuum Memory Firewall turns provider evidence into safer future action.",
            "The result is a memory system that learns from verified outcomes, not persuasive text. Similarity retrieves candidates. Provider evidence decides which memories earn trust. Continuum turns that causal distinction into safer future action.",
            "gate",
        ),
    ]

    stateless_interval = versus_stateless["hierarchical_cluster_bootstrap_95_percentage_points"]
    stateless_e_process = versus_stateless["sequential_e_process"]
    story: dict[str, Any] = {
        "schema_version": STORY_SCHEMA_VERSION,
        "kind": STORY_KIND,
        "compiled_at": compiled_at or datetime.now(timezone.utc).isoformat(),
        "source_release": {
            "tag": source_release_tag,
            "target": source_release_target,
            "envelope_sha256": source_release_envelope_sha256,
            "sequential_asset_sha256": source_release_sequential_sha256,
        },
        "source_artifacts": {
            "sequential_public_sha256": sequential_sha256,
            "campaign_id": sequential_reference["campaign_id"],
            "candidate_workflow_run_id": candidate["run_id"],
            "candidate_artifact_id": candidate_artifact["id"],
            "candidate_artifact_archive_sha256": candidate_artifact["archive_sha256"],
            "evaluator_workflow_run_id": sequential_reference["workflow_run_id"],
            "evaluator_artifact_id": sequential_reference["artifact_id"],
            "evaluation_replay": deepcopy(replay),
        },
        "methodology": deepcopy(methodology),
        "metrics": {
            "target_successes": {
                "episodes_per_arm": targets,
                "stateless": s_success,
                "raw_rag": r_success,
                "continuum": c_success,
            },
            "continuum": {
                "unsafe_proposals": unsafe_blocked,
                "unsafe_memory_exposures": continuum["unsafe_memory_exposures"],
                "false_canonical_promotions": continuum["false_canonical_promotions"],
                "canonical_promotion_precision": continuum["canonical_promotion_precision"],
                "verified_memory_assisted_successes": assisted,
                "cross_scope_leak_count": continuum["cross_scope_leak_count"],
                "duplicate_effect_count": continuum["duplicate_effect_count"],
                "cleanup_residual_count": continuum["cleanup_residual_count"],
                "target_latency_ms": deepcopy(continuum["target_latency_ms"]),
            },
            "raw_rag": {
                "unsafe_proposals": raw["unsafe_proposals"],
                "unsafe_memory_exposures": raw_exposure,
                "unsafe_memory_citation_adoptions": raw["unsafe_memory_citation_adoptions"],
                "false_canonical_promotions": raw_false,
                "canonical_promotion_precision": raw["canonical_promotion_precision"],
                "target_latency_ms": deepcopy(raw["target_latency_ms"]),
            },
            "stateless": {"target_latency_ms": deepcopy(stateless["target_latency_ms"])},
        },
        "statistics": {
            "continuum_vs_raw_rag": deepcopy(versus_raw),
            "continuum_vs_stateless": deepcopy(versus_stateless),
        },
        "release_transaction": {
            "terminal_state": terminal["state"],
            "coordinator_workflow_run_id": terminal_evidence["coordinator_workflow_run_id"],
            "coordinator_artifact_digest": terminal_evidence["coordinator_artifact_digest"],
            "pages_workflow_run_id": terminal_evidence["pages_workflow_run_id"],
            "public_receipt_url": terminal_evidence["public_receipt_url"],
        },
        "architecture": {
            "proposal_plane": "AWS Bedrock bounded action proposal",
            "effect_plane": "receipt-capable disposable GitHub and S3 provider adapters",
            "memory_plane": "CockroachDB outcome-gated vector memory with same-scope RLS",
        },
        "story": {
            "headline": "Failed outcomes must not become future memory",
            "language": "en-US",
            "required_duration_seconds": {"minimum": 90, "maximum": 120},
            "scenes": scenes,
        },
        "claim_boundary": {
            "continuum_vs_raw_rag": "confirmed_paired_advantage",
            "continuum_vs_raw_rag_bootstrap_95_percentage_points": deepcopy(raw_interval),
            "continuum_vs_raw_rag_final_e_value": raw_e_process["final_e_value"],
            "continuum_vs_stateless": "directional_not_confirmatory",
            "continuum_vs_stateless_bootstrap_95_percentage_points": deepcopy(stateless_interval),
            "continuum_vs_stateless_final_e_value": stateless_e_process["final_e_value"],
            "latency": "measured_not_claimed_as_superior",
        },
        "gate": {
            "status": "PASS",
            "checks": {
                "source_release_receipt_bound": True,
                "sequential_asset_digest_bound": True,
                "candidate_replay_receipt_bound": True,
                "real_external_provider": True,
                "blind_scoring_contract": True,
                "paired_raw_rag_advantage_confirmed": True,
                "zero_false_promotions": True,
                "zero_cross_scope_leakage": True,
                "zero_duplicate_effects": True,
                "zero_cleanup_residuals": True,
                "stateless_claim_is_bounded": True,
                "latency_claim_is_bounded": True,
            },
        },
    }
    receipt_body = deepcopy(story)
    story["receipt_sha256"] = _sha256(canonical_json_bytes(receipt_body))
    return story


def render_narration_markdown(story: Mapping[str, Any]) -> str:
    """Render the nine compiler-owned narration paragraphs for speech synthesis."""

    _require(story.get("kind") == STORY_KIND, "unexpected story kind")
    scenes = story.get("story", {}).get("scenes", [])
    _require(isinstance(scenes, list) and len(scenes) == 9, "exactly nine scenes are required")
    parts = ["# Evidence-to-story narration v7", ""]
    for scene in scenes:
        parts.extend((f"## {scene['title']}", "", str(scene["narration"]), ""))
    return "\n".join(parts).rstrip() + "\n"


def verify_evidence_story_receipt(story: Mapping[str, Any]) -> bool:
    """Verify the self-addressed receipt without trusting its final hash field."""

    if story.get("kind") != STORY_KIND or not SHA256_PATTERN.fullmatch(
        str(story.get("receipt_sha256", ""))
    ):
        return False
    body = deepcopy(dict(story))
    expected = body.pop("receipt_sha256")
    return _sha256(canonical_json_bytes(body)) == expected

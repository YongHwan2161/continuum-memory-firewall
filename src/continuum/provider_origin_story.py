"""Compile the live provider-origin proof into a bounded video story receipt."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

from continuum.blind_holdout import canonical_json_bytes
from continuum.outcome_replay_proof import (
    PUBLIC_KIND as OUTCOME_PUBLIC_KIND,
    validate_outcome_replay_proof,
)
from scripts.offline_judge_capsule import verify_envelope_binding
from scripts.release_transaction_coordinator import verify_receipt


STORY_KIND = "continuum.provider-origin-video-story"
STORY_SCHEMA_VERSION = 1
AUTHOR_PREDICATE = "https://slsa.dev/provenance/v1"
PLATFORM_PREDICATE = "https://in-toto.io/attestation/release/v0.2"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _without_receipt(story: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in story.items() if key != "receipt_sha256"}


def story_receipt_sha256(story: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(_without_receipt(story)))


def _statement(bundle: Mapping[str, Any]) -> dict[str, Any]:
    envelope = bundle.get("dsseEnvelope", bundle)
    payload = envelope.get("payload") if isinstance(envelope, Mapping) else None
    _require(isinstance(payload, str), "attestation bundle payload is missing")
    try:
        statement = json.loads(base64.b64decode(payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("attestation bundle payload is invalid") from error
    _require(isinstance(statement, dict), "attestation statement must be an object")
    return statement


def _network_contract(
    network_bundle_bytes: bytes,
    *,
    envelope_sha256: str,
    release_tag: str,
    release_target: str,
) -> dict[str, int]:
    bundles: list[dict[str, Any]] = []
    for line in network_bundle_bytes.decode("utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        _require(isinstance(value, dict), "network bundle line must be an object")
        bundles.append(value)
    statements = [_statement(bundle) for bundle in bundles]
    author = [
        statement
        for statement in statements
        if statement.get("predicateType") == AUTHOR_PREDICATE
        and statement.get("subject")
        == [
            {
                "name": "continuum-release-envelope-v2.json",
                "digest": {"sha256": envelope_sha256},
            }
        ]
    ]
    release_uri = (
        "pkg:github/YongHwan2161/continuum-memory-firewall@" + release_tag
    )
    platform = []
    for statement in statements:
        if statement.get("predicateType") != PLATFORM_PREDICATE:
            continue
        subjects = statement.get("subject", [])
        if not isinstance(subjects, list):
            continue
        envelope_bound = any(
            isinstance(subject, dict)
            and subject.get("name") == "continuum-release-envelope-v2.json"
            and subject.get("digest", {}).get("sha256") == envelope_sha256
            for subject in subjects
        )
        release_bound = any(
            isinstance(subject, dict)
            and subject.get("uri") == release_uri
            and subject.get("digest", {}).get("sha1") == release_target
            for subject in subjects
        )
        if envelope_bound and release_bound:
            platform.append(statement)
    _require(len(bundles) == 2, "exactly two network attestations are required")
    _require(len(author) == 1, "exactly one author attestation is required")
    _require(len(platform) == 1, "exactly one platform countersignature is required")
    return {
        "total": len(bundles),
        "author": len(author),
        "platform": len(platform),
    }


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


def build_provider_origin_story(
    outcome: Mapping[str, Any],
    envelope: Mapping[str, Any],
    capsule: dict[str, Any],
    transaction: Mapping[str, Any],
    *,
    outcome_bytes: bytes,
    envelope_bytes: bytes,
    capsule_bytes: bytes,
    transaction_bytes: bytes,
    network_bundle_bytes: bytes,
    compiled_at: str | None = None,
) -> dict[str, Any]:
    """Build a self-addressed story only after every v27 source binding passes."""

    validate_outcome_replay_proof(outcome, allowed_kinds=(OUTCOME_PUBLIC_KIND,))
    verify_receipt(transaction)
    capsule_result = verify_envelope_binding(
        capsule=capsule,
        capsule_bytes=capsule_bytes,
        envelope=dict(envelope),
    )

    release = envelope.get("release", {})
    release_tag = str(release.get("tag", ""))
    release_target = str(release.get("commit_sha", ""))
    envelope_sha = _sha256(envelope_bytes)
    outcome_sha = _sha256(outcome_bytes)
    capsule_sha = _sha256(capsule_bytes)
    transaction_file_sha = _sha256(transaction_bytes)
    network_sha = _sha256(network_bundle_bytes)
    _require(release_tag == "hackathon-v27", "provider story requires immutable v27")
    _require(SHA_PATTERN.fullmatch(release_target) is not None, "release target is invalid")
    _require(envelope.get("schema_version") == 2, "release envelope schema 2 is required")
    _require(envelope.get("gates", {}).get("status") == "PASS", "release envelope gate failed")
    _require(
        all(envelope.get("gates", {}).get("checks", {}).values()),
        "release envelope contains a failed check",
    )
    _require(
        outcome_sha == envelope.get("outcome_replay_cas", {}).get("public_sha256"),
        "outcome proof bytes are not bound by the release envelope",
    )
    _require(
        release.get("assets", {}).get("outcome_replay_cas", "").endswith(
            f"/{release_tag}/outcome-replay-cas-v1.json"
        ),
        "outcome proof immutable asset URL is missing",
    )
    _require(
        outcome.get("source_head") == envelope.get("outcome_replay_cas", {}).get("head_sha"),
        "outcome proof source head mismatch",
    )
    _require(transaction.get("state") == "PAGES_MATERIALIZED", "release transaction is not terminal")
    _require(transaction.get("release_tag") == release_tag, "transaction release tag mismatch")
    _require(transaction.get("source_digest") == release_target, "transaction target mismatch")
    _require(transaction.get("envelope_sha256") == envelope_sha, "transaction envelope mismatch")
    _require(
        SHA256_PATTERN.fullmatch(str(transaction.get("receipt_sha256", ""))) is not None,
        "transaction receipt digest is invalid",
    )
    terminal = transaction.get("events", [])[-1]
    terminal_evidence = terminal.get("evidence", {})
    _require(terminal.get("state") == "PAGES_MATERIALIZED", "terminal event is invalid")
    _require(terminal_evidence.get("status") == "success", "Pages materialization failed")
    _require(
        terminal_evidence.get("offline_judge_capsule_sha256") == capsule_sha,
        "terminal receipt capsule digest mismatch",
    )
    _require(
        terminal_evidence.get("offline_judge_capsule_receipt_sha256")
        == capsule.get("receipt_sha256"),
        "terminal receipt capsule self-receipt mismatch",
    )
    _require(
        terminal_evidence.get("public_bundle_sha256") == network_sha,
        "terminal receipt network bundle mismatch",
    )
    _require(
        capsule_result.get("online_check_count") == 44
        and capsule_result.get("ui_check_count") == 37
        and capsule_result.get("github_api_requests_per_judge_click") == 0,
        "offline capsule does not carry the 44/37/zero-API contract",
    )
    _require(
        capsule.get("online_verification", {}).get("checks", {}).get(
            "outcome_replay_cas_closure"
        )
        is True,
        "offline capsule omitted outcome replay closure",
    )
    attestations = _network_contract(
        network_bundle_bytes,
        envelope_sha256=envelope_sha,
        release_tag=release_tag,
        release_target=release_target,
    )

    provider = outcome["provider"]
    attestation = outcome["attestation"]
    cas = outcome["cas"]
    rls = outcome["database"]["rls"]
    negative_count = len(attestation["negative_codes"])
    _require(provider["lookup_count"] == 7, "seven provider lookups are required")
    _require(attestation["ttl_seconds"] == 300, "five-minute handle is required")
    _require(negative_count == 6, "six negative authority controls are required")
    _require(attestation["negative_outcome_rows"] == 0, "negative authority produced an outcome")
    _require(cas["outcome_rows"] == 1, "exactly one outcome row is required")
    _require(cas["canonical_promotions"] == 1, "exactly one canonical promotion is required")
    _require(attestation["atomic_join_rows"] == 1, "exactly one atomic join is required")
    _require(attestation["raw_handle_persisted"] is False, "raw handle was persisted")
    _require(rls["runtime_attestation_insert_sqlstate"] == "42501", "RLS insert denial is absent")
    _require(
        [entry["decision"] for entry in cas["journal"]]
        == ["accepted", "exact_replay", "conflict"],
        "replay journal decision sequence changed",
    )

    handle_minutes = attestation["ttl_seconds"] // 60
    coordinator_run = int(terminal_evidence["coordinator_workflow_run_id"])
    pages_run = int(terminal_evidence["pages_workflow_run_id"])
    scenes = [
        _scene(
            "problem",
            "The worker must not declare its own success",
            "A persuasive model output is not provider truth.",
            "An agent may confidently report success even when the external effect never happened. If that claim becomes canonical memory, one hallucination silently changes every action that follows. Continuum moves success authority outside the action worker.",
            "claim_boundary",
        ),
        _scene(
            "provider_reread",
            "Re-read the real provider",
            f"S3 HeadObject + GetObject · {provider['lookup_count']} fresh lookups.",
            f"For the retained live proposal, an independent verifier re-read Amazon S3 with HeadObject and GetObject. Seven fresh lookups established the accepted receipt and a conflicting receipt from the real provider, not from model text.",
            "provider",
        ),
        _scene(
            "short_lived_handle",
            "Issue a bound, short-lived capability",
            f"{handle_minutes}-minute handle · proposal + provider + receipt + nonce.",
            f"Only after that lookup did the verifier issue a {handle_minutes}-minute promotion handle. It binds the proposal, provider, idempotency key, receipt digest, success status, policy, key ID, nonce, issue time, and expiry.",
            "attestation",
        ),
        _scene(
            "atomic_promotion",
            "Consume authority atomically",
            "1 attestation · 1 outcome · 1 canonical memory · 1 transaction.",
            "CockroachDB consumed the handle digest and nonce in the same transaction as exactly one verified outcome and one canonical memory. There was one atomic attestation, outcome, and memory join, while the raw signed handle was never persisted.",
            "attestation.atomic_join_rows",
            "cas.outcome_rows",
            "cas.canonical_promotions",
        ),
        _scene(
            "negative_matrix",
            "Invalid authority cannot create memory",
            f"Missing · forged · expired · cross-bound · mismatch blocked {negative_count}/{negative_count}.",
            "We then attacked the authority boundary. Missing, forged, expired, cross-proposal, cross-provider, and receipt-mismatched handles were all rejected. Six of six invalid paths produced zero negative outcome rows.",
            "attestation.negative_codes",
            "attestation.negative_outcome_rows",
        ),
        _scene(
            "rls_and_replay",
            "RLS and replay stay fail-closed",
            "Read 1 · insert denied 42501 · accepted → exact replay → conflict.",
            "The scope SQL identity could read its one attestation row but could not mint one; CockroachDB returned SQLSTATE four two five zero one. Exact replay returned the durable identity, while a different real receipt committed an explicit conflict journal entry.",
            "database.rls",
            "cas.journal",
        ),
        _scene(
            "architecture",
            "A causal memory contract",
            "Bedrock proposes · S3 proves · CockroachDB promotes and retrieves.",
            "Amazon Bedrock generates only bounded action proposals. The provider verifier establishes the external effect. CockroachDB joins episode state, row-level security, transactional promotion, and vector retrieval, so future agents can retrieve only outcome-earned memory in their server-owned scope.",
            "architecture",
        ),
        _scene(
            "immutable_proof",
            "The judge path survives API failure",
            f"{release_tag} · 1 author + 1 platform attestation · 44 checks · 0 API calls.",
            f"Immutable release {release_tag} binds these bytes to coordinator run {coordinator_run} and Pages run {pages_run}. It carries one author Sigstore attestation and one GitHub release countersignature. Even with anonymous API quota exhausted, the public judge path passed all forty-four checks with zero GitHub API requests.",
            "release",
            "network_attestations",
            "offline_capsule",
            "release_transaction",
        ),
        _scene(
            "close",
            "Similarity retrieves. Provider outcomes earn trust.",
            "The model proposes. The provider proves. CockroachDB remembers.",
            "This is the difference: the model may propose an action, but it cannot certify its own success. Provider evidence earns memory authority, and CockroachDB makes that authority transactional, isolated, replay-safe, and publicly verifiable.",
            "gate",
        ),
    ]

    story: dict[str, Any] = {
        "schema_version": STORY_SCHEMA_VERSION,
        "kind": STORY_KIND,
        "compiled_at": compiled_at or datetime.now(timezone.utc).isoformat(),
        "source_release": {
            "tag": release_tag,
            "target": release_target,
            "envelope_sha256": envelope_sha,
            "outcome_asset_sha256": outcome_sha,
            "capsule_sha256": capsule_sha,
            "network_bundle_sha256": network_sha,
            "transaction_file_sha256": transaction_file_sha,
            "transaction_receipt_sha256": transaction["receipt_sha256"],
        },
        "live_proof": {
            "source_head": outcome["source_head"],
            "workflow_run_id": outcome["workflow"]["run_id"],
            "migration_version": outcome["migration"]["current_version"],
            "provider": deepcopy(provider),
            "attestation": deepcopy(attestation),
            "cas": {
                "outcome_rows": cas["outcome_rows"],
                "canonical_promotions": cas["canonical_promotions"],
                "journal_rows": cas["journal_rows"],
                "decisions": [entry["decision"] for entry in cas["journal"]],
                "chain_tip": cas["chain_tip"],
                "conflict_error_code": cas["conflict_error_code"],
            },
            "rls": deepcopy(rls),
            "gate": deepcopy(outcome["gate"]),
        },
        "release_proof": {
            "coordinator_workflow_run_id": coordinator_run,
            "coordinator_artifact_id": terminal_evidence["coordinator_artifact_id"],
            "coordinator_artifact_digest": terminal_evidence["coordinator_artifact_digest"],
            "pages_workflow_run_id": pages_run,
            "terminal_state": transaction["state"],
            "online_check_count": capsule_result["online_check_count"],
            "ui_check_count": capsule_result["ui_check_count"],
            "judge_github_api_requests": capsule_result[
                "github_api_requests_per_judge_click"
            ],
            "network_attestations": attestations,
        },
        "architecture": {
            "proposal_plane": "Amazon Bedrock bounded action proposal",
            "provider_truth_plane": "fresh Amazon S3 receipt lookup by an independent verifier",
            "memory_plane": "CockroachDB atomic outcome promotion, RLS, and vector retrieval",
        },
        "story": {
            "headline": "The action worker cannot certify its own success",
            "language": "en-US",
            "required_duration_seconds": {"minimum": 90, "maximum": 120},
            "scenes": scenes,
        },
        "claim_boundary": {
            "admitted": (
                "One retained participant-cluster S3 proposal proves provider-origin "
                "admission, exact binding, short expiry, atomic consumption, replay, "
                "RLS, immutable publication, and credential-free judge delivery."
            ),
            "excluded": [
                "population-level effect estimate",
                "durable signing-key custody",
                "rotation continuity across verifier restarts",
            ],
        },
        "gate": {
            "status": "PASS",
            "checks": {
                "outcome_public_proof_valid": True,
                "provider_lookup_precedes_issue": True,
                "short_lived_handle_bound": True,
                "atomic_promotion_proven": True,
                "six_negative_authority_paths_blocked": True,
                "rls_insert_denied": True,
                "replay_conflict_journaled": True,
                "immutable_release_bound": True,
                "network_sign_once_contract_bound": True,
                "quota_independent_judge_bound": True,
                "claim_boundary_explicit": True,
            },
        },
    }
    story["receipt_sha256"] = story_receipt_sha256(story)
    verify_provider_origin_story(story)
    return story


def verify_provider_origin_story(story: Mapping[str, Any]) -> None:
    if story.get("schema_version") != STORY_SCHEMA_VERSION or story.get("kind") != STORY_KIND:
        raise RuntimeError("provider-origin story schema is invalid")
    if story.get("receipt_sha256") != story_receipt_sha256(story):
        raise RuntimeError("provider-origin story receipt hash mismatch")
    source = story.get("source_release", {})
    if source.get("tag") != "hackathon-v27" or not SHA_PATTERN.fullmatch(
        str(source.get("target", ""))
    ):
        raise RuntimeError("provider-origin story release identity is invalid")
    for field in (
        "envelope_sha256",
        "outcome_asset_sha256",
        "capsule_sha256",
        "network_bundle_sha256",
        "transaction_file_sha256",
        "transaction_receipt_sha256",
    ):
        if not SHA256_PATTERN.fullmatch(str(source.get(field, ""))):
            raise RuntimeError(f"provider-origin story {field} is invalid")
    live = story.get("live_proof", {})
    release = story.get("release_proof", {})
    if live.get("provider", {}).get("lookup_count") != 7:
        raise RuntimeError("provider-origin story lookup count changed")
    if live.get("attestation", {}).get("atomic_join_rows") != 1:
        raise RuntimeError("provider-origin story atomic join changed")
    if live.get("attestation", {}).get("negative_outcome_rows") != 0:
        raise RuntimeError("provider-origin story contains a negative outcome")
    if len(live.get("attestation", {}).get("negative_codes", {})) != 6:
        raise RuntimeError("provider-origin story negative matrix changed")
    if live.get("cas", {}).get("decisions") != ["accepted", "exact_replay", "conflict"]:
        raise RuntimeError("provider-origin story replay sequence changed")
    if live.get("rls", {}).get("runtime_attestation_insert_sqlstate") != "42501":
        raise RuntimeError("provider-origin story RLS denial changed")
    if release.get("online_check_count") != 44 or release.get("ui_check_count") != 37:
        raise RuntimeError("provider-origin story judge counts changed")
    if release.get("judge_github_api_requests") != 0:
        raise RuntimeError("provider-origin story judge path is not quota independent")
    if release.get("network_attestations") != {"total": 2, "author": 1, "platform": 1}:
        raise RuntimeError("provider-origin story attestation counts changed")
    scenes = story.get("story", {}).get("scenes", [])
    if len(scenes) != 9 or any(not scene.get("narration") for scene in scenes):
        raise RuntimeError("provider-origin story requires nine narrated scenes")
    gate = story.get("gate", {})
    checks = gate.get("checks", {})
    if gate.get("status") != "PASS" or not checks or not all(checks.values()):
        raise RuntimeError("provider-origin story gate failed")


def render_narration_markdown(story: Mapping[str, Any]) -> str:
    verify_provider_origin_story(story)
    lines = ["# Provider-origin outcome authority narration v8", ""]
    for scene in story["story"]["scenes"]:
        lines.extend((f"## {scene['title']}", "", str(scene["narration"]), ""))
    return "\n".join(lines).rstrip() + "\n"

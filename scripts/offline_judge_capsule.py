"""Build and verify a quota-independent judge evidence capsule.

The capsule preserves the result of the complete online read-only verifier inside
the next immutable release.  A browser can therefore verify the frozen provider
snapshot, release-envelope binding, and terminal receipt without calling the
GitHub API.  The scheduled monitor remains responsible for refreshing live
provider state after publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.release_transaction_coordinator import verify_receipt


CAPSULE_KIND = "continuum.offline-judge-capsule.v1"
CAPSULE_ASSET_NAME = "judge-offline-capsule-v1.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# This mapping is deliberately explicit.  It prevents a compiler from turning a
# single aggregate PASS into forty friendly-looking claims without preserving
# which underlying online verifier checks support each row shown to a judge.
UI_CHECK_SOURCES: dict[str, tuple[str, ...]] = {
    "bundle": ("release_envelope_gate",),
    "workflow": ("workflow_succeeded",),
    "head": ("workflow_head_matches",),
    "health": ("mcp_health_ok", "mcp_service_matches"),
    "pages": ("public_demo_marker_present", "release_transaction_terminal"),
    "story": ("live_story_bound",),
    "scope": ("cross_scope_fetch_denied", "zero_cross_scope_leakage"),
    "control": ("tenant_control_plane_active",),
    "pool": ("bounded_database_pools",),
    "index": ("scoped_vector_index_contract",),
    "migration": ("migration_capability_absent",),
    "scale": ("representative_scale_gate",),
    "ann": ("natural_ann_without_full_scan",),
    "benchmark": ("benchmark_workflow_matches_report",),
    "scaleScope": ("benchmark_scope_isolation",),
    "pressure": ("agent_pressure_gate",),
    "pressureLineage": ("agent_pressure_lineage",),
    "pressureCorrectness": ("agent_pressure_correctness",),
    "ablation": ("ablation_lineage_and_population",),
    "drilldown": ("episode_drilldown_projection",),
    "grounding": ("citation_handle_grounding",),
    "memoryPolicy": ("paired_memory_policy_differentiates",),
    "guardian": ("real_provider_release_guardian",),
    "replication": ("time_distributed_real_provider_replication",),
    "blind": ("preregistered_blind_holdout",),
    "sequential": ("sequential_blind_memory_compounding",),
    "ciRecovery": ("real_ci_closed_loop_recovery",),
    "adaptiveDiagnosis": ("preregistered_adaptive_diagnosis",),
    "transferFirewall": (
        "counterfactual_cross_environment_transfer_firewall",
    ),
    "onlineLineage": ("online_memory_lineage_closure",),
    "outcomeCas": ("outcome_replay_cas_closure",),
    "evidenceStory": ("receipt_compiled_evidence_story",),
    "sandbox": ("sandbox_provider_receipt",),
    "rls": ("rls_checksum_bound",),
    "release": ("immutable_release_assets",),
    "provenance": ("network_sign_once_subject_visible",),
    "transaction": ("release_transaction_terminal",),
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def capsule_receipt_sha256(capsule: dict[str, Any]) -> str:
    body = deepcopy(capsule)
    body.pop("receipt_sha256", None)
    return sha256_bytes(canonical_json_bytes(body))


def _release_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [
        item
        for item in release.get("assets", [])
        if isinstance(item, dict) and item.get("name") == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"release asset {name!r} is not unique")
    return matches[0]


def _ui_projection(checks: dict[str, Any]) -> dict[str, bool]:
    missing = sorted(
        {
            source
            for sources in UI_CHECK_SOURCES.values()
            for source in sources
            if source not in checks
        }
    )
    if missing:
        raise RuntimeError(
            "online verifier omitted capsule UI sources: " + ", ".join(missing)
        )
    return {
        name: all(checks.get(source) is True for source in sources)
        for name, sources in UI_CHECK_SOURCES.items()
    }


def build_capsule(
    *,
    evidence_url: str,
    evidence_bytes: bytes,
    verification_report: dict[str, Any],
    predecessor_release: dict[str, Any],
    transaction_receipt: dict[str, Any],
    transaction_bytes: bytes,
    author_bundle_bytes: bytes,
    network_bundle_bytes: bytes,
    compiler_repository: str,
    compiler_source_head: str,
    compiler_workflow_run_id: int,
    compiler_workflow_attempt: int,
    compiler_release_tag: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    if not SHA_PATTERN.fullmatch(compiler_source_head):
        raise RuntimeError("capsule compiler source head must be a full SHA")
    if compiler_workflow_run_id < 1 or compiler_workflow_attempt < 1:
        raise RuntimeError("capsule compiler workflow lineage is invalid")
    if not compiler_repository or "/" not in compiler_repository:
        raise RuntimeError("capsule compiler repository is invalid")
    if not compiler_release_tag or any(
        character.isspace() for character in compiler_release_tag
    ):
        raise RuntimeError("capsule successor release tag is invalid")

    checks = verification_report.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise RuntimeError("online verifier checks are absent")
    if verification_report.get("ok") is not True or not all(
        value is True for value in checks.values()
    ):
        raise RuntimeError("online verifier did not pass every gate")
    if verification_report.get("mode") != "read-only-http-get":
        raise RuntimeError("unexpected online verifier mode")
    ui_checks = _ui_projection(checks)

    release_reference = json.loads(evidence_bytes.decode("utf-8"))["release_envelope"]
    release_tag = release_reference["tag"]
    release_target = predecessor_release.get("target_commitish")
    if predecessor_release.get("immutable") is not True:
        raise RuntimeError("predecessor release is not immutable")
    if predecessor_release.get("draft") is not False:
        raise RuntimeError("predecessor release is still a draft")
    if predecessor_release.get("tag_name") != release_tag:
        raise RuntimeError("predecessor release tag does not match public evidence")
    if not isinstance(release_target, str) or not SHA_PATTERN.fullmatch(release_target):
        raise RuntimeError("predecessor release target is invalid")
    if release_tag == compiler_release_tag:
        raise RuntimeError("capsule must carry forward a prior immutable release")

    envelope_asset = _release_asset(
        predecessor_release, release_reference["asset_name"]
    )
    author_asset = _release_asset(
        predecessor_release,
        json.loads(evidence_bytes.decode("utf-8"))["network_sign_once"][
            "author_bundle_asset_name"
        ],
    )
    envelope_sha = str(envelope_asset.get("digest", "")).removeprefix("sha256:")
    author_sha = sha256_bytes(author_bundle_bytes)
    network_sha = sha256_bytes(network_bundle_bytes)
    if not SHA256_PATTERN.fullmatch(envelope_sha):
        raise RuntimeError("predecessor envelope digest is invalid")
    if author_asset.get("digest") != "sha256:" + author_sha:
        raise RuntimeError("predecessor author bundle is not release-bound")

    verify_receipt(transaction_receipt)
    terminal = transaction_receipt.get("events", [])[-1].get("evidence", {})
    if transaction_receipt.get("state") != "PAGES_MATERIALIZED":
        raise RuntimeError("predecessor transaction is not terminal")
    if transaction_receipt.get("release_tag") != release_tag:
        raise RuntimeError("predecessor transaction tag mismatch")
    if transaction_receipt.get("source_digest") != release_target:
        raise RuntimeError("predecessor transaction target mismatch")
    if transaction_receipt.get("envelope_sha256") != envelope_sha:
        raise RuntimeError("predecessor transaction envelope mismatch")
    if terminal.get("public_bundle_sha256") != network_sha:
        raise RuntimeError("predecessor network bundle is not terminal-bound")

    author_event = next(
        (
            event.get("evidence", {})
            for event in transaction_receipt.get("events", [])
            if event.get("state") == "AUTHOR_ATTESTED"
        ),
        {},
    )
    if author_event.get("author_bundle_sha256") != author_sha:
        raise RuntimeError("predecessor author bundle is not transaction-bound")

    gate_checks = {
        "full_online_verifier_passed": True,
        "all_online_checks_passed": all(checks.values()),
        "ui_projection_complete": all(ui_checks.values()),
        "predecessor_release_immutable": predecessor_release.get("immutable") is True,
        "predecessor_envelope_bound": transaction_receipt.get("envelope_sha256")
        == envelope_sha,
        "predecessor_author_bundle_bound": author_event.get(
            "author_bundle_sha256"
        )
        == author_sha,
        "predecessor_network_bundle_bound": terminal.get("public_bundle_sha256")
        == network_sha,
        "predecessor_transaction_terminal": transaction_receipt.get("state")
        == "PAGES_MATERIALIZED",
        "browser_github_api_requests_zero": True,
    }
    if not all(gate_checks.values()):
        raise RuntimeError("offline capsule gates did not close")

    capsule: dict[str, Any] = {
        "schema_version": 1,
        "kind": CAPSULE_KIND,
        "observed_at": observed_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "claim_boundary": (
            "The capsule freezes a complete online verifier PASS for the prior "
            "immutable release. It removes GitHub API calls from the judge click; "
            "scheduled monitors remain the source of later live freshness."
        ),
        "compiler": {
            "repository": compiler_repository,
            "source_head": compiler_source_head,
            "workflow_run_id": compiler_workflow_run_id,
            "workflow_attempt": compiler_workflow_attempt,
            "workflow": (
                f"{compiler_repository}/.github/workflows/release-envelope.yml"
            ),
            "successor_release_tag": compiler_release_tag,
        },
        "predecessor": {
            "evidence_url": evidence_url,
            "evidence_sha256": sha256_bytes(evidence_bytes),
            "release_tag": release_tag,
            "release_target": release_target,
            "release_envelope_sha256": envelope_sha,
            "transaction_receipt_sha256": transaction_receipt["receipt_sha256"],
            "transaction_file_sha256": sha256_bytes(transaction_bytes),
            "author_bundle_sha256": author_sha,
            "network_bundle_sha256": network_sha,
        },
        "online_verification": {
            "mode": verification_report["mode"],
            "ok": True,
            "check_count": len(checks),
            "checks": checks,
            "workflow_run_id": verification_report.get("workflow_run_id"),
            "vector_benchmark_run_id": verification_report.get(
                "vector_benchmark_run_id"
            ),
            "agent_pressure_run_id": verification_report.get(
                "agent_pressure_run_id"
            ),
            "agent_ablation_run_id": verification_report.get(
                "agent_ablation_run_id"
            ),
            "deployment_head_sha": verification_report.get("deployment_head_sha"),
        },
        "ui_check_sources": {
            name: list(sources) for name, sources in UI_CHECK_SOURCES.items()
        },
        "ui_checks": ui_checks,
        "request_policy": {
            "judge_click_github_api_requests": 0,
            "judge_click_credentials_required": False,
            "same_origin_static_gets_only": True,
            "live_refresh_owner": "judge-path-monitor.yml",
        },
        "gate": {"status": "PASS", "checks": gate_checks},
    }
    capsule["receipt_sha256"] = capsule_receipt_sha256(capsule)
    verify_capsule(capsule)
    return capsule


def verify_capsule(capsule: dict[str, Any]) -> dict[str, Any]:
    if capsule.get("schema_version") != 1 or capsule.get("kind") != CAPSULE_KIND:
        raise RuntimeError("offline judge capsule schema is unsupported")
    if capsule.get("receipt_sha256") != capsule_receipt_sha256(capsule):
        raise RuntimeError("offline judge capsule receipt hash mismatch")
    compiler = capsule.get("compiler", {})
    predecessor = capsule.get("predecessor", {})
    online = capsule.get("online_verification", {})
    request_policy = capsule.get("request_policy", {})
    checks = online.get("checks", {})
    if not SHA_PATTERN.fullmatch(str(compiler.get("source_head", ""))):
        raise RuntimeError("offline judge capsule compiler source is invalid")
    for field in (
        "evidence_sha256",
        "release_envelope_sha256",
        "transaction_receipt_sha256",
        "transaction_file_sha256",
        "author_bundle_sha256",
        "network_bundle_sha256",
    ):
        if not SHA256_PATTERN.fullmatch(str(predecessor.get(field, ""))):
            raise RuntimeError(f"offline judge capsule {field} is invalid")
    if not SHA_PATTERN.fullmatch(str(predecessor.get("release_target", ""))):
        raise RuntimeError("offline judge capsule predecessor target is invalid")
    if online.get("ok") is not True or online.get("mode") != "read-only-http-get":
        raise RuntimeError("offline judge capsule online verifier did not pass")
    if not isinstance(checks, dict) or not checks or not all(
        value is True for value in checks.values()
    ):
        raise RuntimeError("offline judge capsule contains a failed online check")
    if online.get("check_count") != len(checks):
        raise RuntimeError("offline judge capsule check count mismatch")
    expected_sources = {
        name: list(sources) for name, sources in UI_CHECK_SOURCES.items()
    }
    if capsule.get("ui_check_sources") != expected_sources:
        raise RuntimeError("offline judge capsule UI source mapping changed")
    expected_ui = _ui_projection(checks)
    if capsule.get("ui_checks") != expected_ui or not all(expected_ui.values()):
        raise RuntimeError("offline judge capsule UI projection failed")
    if request_policy != {
        "judge_click_github_api_requests": 0,
        "judge_click_credentials_required": False,
        "same_origin_static_gets_only": True,
        "live_refresh_owner": "judge-path-monitor.yml",
    }:
        raise RuntimeError("offline judge capsule request policy changed")
    gate = capsule.get("gate", {})
    gate_checks = gate.get("checks", {})
    if gate.get("status") != "PASS" or not gate_checks or not all(
        value is True for value in gate_checks.values()
    ):
        raise RuntimeError("offline judge capsule gate failed")
    return {
        "ok": True,
        "receipt_sha256": capsule["receipt_sha256"],
        "online_check_count": len(checks),
        "ui_check_count": len(expected_ui),
        "github_api_requests_per_judge_click": 0,
    }


def verify_envelope_binding(
    *,
    capsule: dict[str, Any],
    capsule_bytes: bytes,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    result = verify_capsule(capsule)
    reference = envelope.get("offline_judge_capsule", {})
    compiler = capsule["compiler"]
    if reference.get("schema_version") != 1:
        raise RuntimeError("release envelope omitted offline judge capsule")
    if reference.get("asset_name") != CAPSULE_ASSET_NAME:
        raise RuntimeError("release envelope capsule asset name mismatch")
    if reference.get("asset_sha256") != sha256_bytes(capsule_bytes):
        raise RuntimeError("release envelope capsule file digest mismatch")
    if reference.get("receipt_sha256") != capsule.get("receipt_sha256"):
        raise RuntimeError("release envelope capsule receipt mismatch")
    if envelope.get("release", {}).get("commit_sha") != compiler.get("source_head"):
        raise RuntimeError("release envelope capsule source mismatch")
    if envelope.get("release", {}).get("tag") != compiler.get(
        "successor_release_tag"
    ):
        raise RuntimeError("release envelope capsule successor tag mismatch")
    return {**result, "asset_sha256": reference["asset_sha256"]}


def _build_from_network(args: argparse.Namespace) -> dict[str, Any]:
    # Lazy import keeps verify_capsule usable by judge_readonly_verify without a
    # circular module import.
    from scripts.judge_readonly_verify import _get_bytes, get_json, verify_evidence

    evidence_bytes = _get_bytes(args.evidence_url)
    evidence = json.loads(evidence_bytes.decode("utf-8"))
    if not isinstance(evidence, dict):
        raise RuntimeError("public judge evidence must be a JSON object")
    verification_report = verify_evidence(evidence)
    predecessor_release = get_json(evidence["release_envelope"]["release_api_url"])
    transaction_url = evidence["release_transaction"]["public_receipt_url"]
    transaction_bytes = _get_bytes(transaction_url)
    transaction_receipt = json.loads(transaction_bytes.decode("utf-8"))
    author_bundle_bytes = _get_bytes(
        evidence["network_sign_once"]["author_bundle_public_url"]
    )
    network_bundle_bytes = _get_bytes(
        evidence["network_sign_once"]["network_bundle_public_url"]
    )
    capsule = build_capsule(
        evidence_url=args.evidence_url,
        evidence_bytes=evidence_bytes,
        verification_report=verification_report,
        predecessor_release=predecessor_release,
        transaction_receipt=transaction_receipt,
        transaction_bytes=transaction_bytes,
        author_bundle_bytes=author_bundle_bytes,
        network_bundle_bytes=network_bundle_bytes,
        compiler_repository=args.repository,
        compiler_source_head=args.source_head,
        compiler_workflow_run_id=args.workflow_run_id,
        compiler_workflow_attempt=args.workflow_attempt,
        compiler_release_tag=args.release_tag,
        observed_at=args.observed_at,
    )
    encoded = (json.dumps(capsule, indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{sha256_bytes(encoded)}  {args.output.name}\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "asset_sha256": sha256_bytes(encoded),
        "receipt_sha256": capsule["receipt_sha256"],
        "predecessor_release_tag": capsule["predecessor"]["release_tag"],
        "successor_release_tag": capsule["compiler"]["successor_release_tag"],
        "online_check_count": capsule["online_verification"]["check_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--evidence-url", required=True)
    build.add_argument("--repository", required=True)
    build.add_argument("--source-head", required=True)
    build.add_argument("--workflow-run-id", type=int, required=True)
    build.add_argument("--workflow-attempt", type=int, required=True)
    build.add_argument("--release-tag", required=True)
    build.add_argument("--observed-at")
    build.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--capsule", type=Path, required=True)
    verify.add_argument("--envelope", type=Path)

    args = parser.parse_args()
    if args.command == "build":
        result = _build_from_network(args)
    else:
        capsule_bytes = args.capsule.read_bytes()
        capsule = json.loads(capsule_bytes.decode("utf-8"))
        if args.envelope is None:
            result = verify_capsule(capsule)
        else:
            envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
            result = verify_envelope_binding(
                capsule=capsule,
                capsule_bytes=capsule_bytes,
                envelope=envelope,
            )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

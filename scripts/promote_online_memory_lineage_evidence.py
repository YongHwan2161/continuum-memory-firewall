"""Promote one exact online memory-lineage recovery into public judge evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from continuum.online_memory_lineage import build_public_online_memory_lineage


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _repository_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_bytes(path: Path) -> tuple[bytes, dict[str, Any]]:
    value = path.read_bytes()
    return value, json.loads(value)


def _parse_time(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as error:
        raise RuntimeError("online lineage timestamp is invalid") from error


def _validate_reconciliation_inputs(
    raw: Mapping[str, Any],
    *,
    reconciliation_input_bytes: bytes,
    reconciliation_input: Mapping[str, Any],
    proposals_bytes: bytes,
    proposals: Mapping[str, Any],
    provider_outcomes_bytes: bytes,
    provider_outcomes: Mapping[str, Any],
) -> None:
    reconciliation = raw["reconciliation"]
    if _sha256(reconciliation_input_bytes) != reconciliation["input_receipt_sha256"]:
        raise RuntimeError("reconciliation input receipt is not exact")
    expected_input = {
        "schema_version": 1,
        "kind": "continuum.online-memory-lineage.reconciliation-input",
        "candidate_source_head": reconciliation["candidate_source_head"],
        "reconciler_source_head": reconciliation["reconciler_source_head"],
        "predecessor_workflow_run_id": reconciliation[
            "predecessor_workflow_run_id"
        ],
        "reconciliation_workflow_run_id": reconciliation[
            "reconciliation_workflow_run_id"
        ],
        "reconciliation_workflow_run_attempt": reconciliation[
            "reconciliation_workflow_run_attempt"
        ],
        "actions_permission": "read",
        "provider_action_dispatch_capability": False,
    }
    if any(reconciliation_input.get(key) != value for key, value in expected_input.items()):
        raise RuntimeError("reconciliation capability lineage is invalid")
    if _sha256(proposals_bytes) != reconciliation_input.get("proposals_sha256"):
        raise RuntimeError("predecessor proposal receipt is not exact")
    if _sha256(provider_outcomes_bytes) != reconciliation_input.get(
        "provider_outcomes_sha256"
    ):
        raise RuntimeError("predecessor outcome receipt is not exact")
    if (
        proposals.get("kind") != "continuum.online-memory-lineage.proposals"
        or proposals.get("source_head") != reconciliation["candidate_source_head"]
        or provider_outcomes.get("kind")
        != "continuum.online-memory-lineage.provider-outcomes"
        or provider_outcomes.get("source_head")
        != reconciliation["candidate_source_head"]
    ):
        raise RuntimeError("predecessor report lineage is invalid")

    raw_targets = {item["case_id"]: item for item in raw["targets"]}
    proposal_targets = {item["case_id"]: item for item in proposals["proposals"]}
    outcome_targets = {item["case_id"]: item for item in provider_outcomes["outcomes"]}
    if not (
        len(raw_targets) == len(proposal_targets) == len(outcome_targets) == 2
        and set(raw_targets) == set(proposal_targets) == set(outcome_targets)
    ):
        raise RuntimeError("predecessor target cardinality is invalid")
    prepared_at = _parse_time(proposals.get("proposal_prepared_at"))
    action_run_ids: set[int] = set()
    for case_id, target in raw_targets.items():
        proposal = proposal_targets[case_id]
        outcome = outcome_targets[case_id]
        provider_receipt = outcome.get("provider_receipt", {})
        if (
            proposal.get("proposal_id") != target.get("proposal_id")
            or proposal.get("run_id") != target.get("run_id")
            or proposal.get("proposed_patch_id") != target.get("proposed_patch_id")
            or provider_receipt != target.get("provider_receipt")
            or _parse_time(provider_receipt.get("created_at")) <= prepared_at
        ):
            raise RuntimeError("provider action did not follow its durable proposal")
        action_run_ids.add(int(provider_receipt["workflow_run_id"]))
    if len(action_run_ids) != 2:
        raise RuntimeError("provider action receipts are not unique")


def build_reference(
    raw: dict[str, Any],
    public: dict[str, Any],
    *,
    public_bytes: bytes,
    reconciliation_input_bytes: bytes,
    reconciliation_input: dict[str, Any],
    proposals_bytes: bytes,
    proposals: dict[str, Any],
    provider_outcomes_bytes: bytes,
    provider_outcomes: dict[str, Any],
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
) -> dict[str, Any]:
    expected_public = build_public_online_memory_lineage(raw)
    if public != expected_public:
        raise RuntimeError("public online lineage is not the raw-report projection")
    _validate_reconciliation_inputs(
        raw,
        reconciliation_input_bytes=reconciliation_input_bytes,
        reconciliation_input=reconciliation_input,
        proposals_bytes=proposals_bytes,
        proposals=proposals,
        provider_outcomes_bytes=provider_outcomes_bytes,
        provider_outcomes=provider_outcomes,
    )
    reconciliation = raw["reconciliation"]
    reconciler_head = str(reconciliation["reconciler_source_head"])
    run_id = int(reconciliation["reconciliation_workflow_run_id"])
    attempt = int(reconciliation["reconciliation_workflow_run_attempt"])
    repository = str(raw["repository"])
    if SHA_PATTERN.fullmatch(reconciler_head) is None:
        raise RuntimeError("online lineage reconciler head is invalid")
    expected_artifact = (
        "continuum-online-memory-lineage-reconciliation-"
        f"{reconciler_head}-{run_id}-{attempt}"
    )
    if artifact_name != expected_artifact or artifact_id < 1:
        raise RuntimeError("online lineage artifact is not exact-run bound")
    if SHA256_PATTERN.fullmatch(artifact_archive_sha256) is None:
        raise RuntimeError("online lineage artifact archive digest is invalid")
    predecessor_digest = str(reconciliation_input["predecessor_artifact_digest"])
    if re.fullmatch(r"sha256:[0-9a-f]{64}", predecessor_digest) is None:
        raise RuntimeError("online lineage predecessor artifact digest is invalid")

    action_run_ids = sorted(
        int(item["provider_receipt"]["workflow_run_id"])
        for item in raw["targets"]
    )
    return {
        "schema_version": 1,
        "candidate_head_sha": reconciliation["candidate_source_head"],
        "reconciler_head_sha": reconciler_head,
        "workflow_run_id": run_id,
        "workflow_attempt": attempt,
        "workflow_url": f"https://github.com/{repository}/actions/runs/{run_id}",
        "workflow_api_url": (
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"
        ),
        "predecessor_workflow_run_id": reconciliation[
            "predecessor_workflow_run_id"
        ],
        "predecessor_workflow_url": (
            f"https://github.com/{repository}/actions/runs/"
            f"{reconciliation['predecessor_workflow_run_id']}"
        ),
        "predecessor_workflow_api_url": (
            f"https://api.github.com/repos/{repository}/actions/runs/"
            f"{reconciliation['predecessor_workflow_run_id']}"
        ),
        "predecessor_artifact_id": int(
            reconciliation_input["predecessor_artifact_id"]
        ),
        "predecessor_artifact_name": reconciliation_input[
            "predecessor_artifact_name"
        ],
        "predecessor_artifact_archive_sha256": predecessor_digest.removeprefix(
            "sha256:"
        ),
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_api_url": (
            f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"
        ),
        "artifact_archive_sha256": artifact_archive_sha256,
        "public_sha256": _sha256(_repository_bytes(public_bytes)),
        "public_url": public_url,
        "page_url": page_url,
        "raw_receipt_sha256": raw["receipt_sha256"],
        "reconciliation_input_sha256": reconciliation[
            "input_receipt_sha256"
        ],
        "proposals_sha256": reconciliation_input["proposals_sha256"],
        "provider_outcomes_sha256": reconciliation_input[
            "provider_outcomes_sha256"
        ],
        "rls_combined_sha256": raw["rls"]["combined_sha256"],
        "source_memory_id": raw["source"]["memory_id"],
        "target_cases": 2,
        "provider_action_run_ids": action_run_ids,
        "provider_action_reexecutions": 0,
        "agent_model": raw["agent_model"],
        "embedding_model": raw["embedding_model"],
    }


def promote(
    *,
    raw_path: Path,
    reconciliation_input_path: Path,
    proposals_path: Path,
    provider_outcomes_path: Path,
    judge_path: Path,
    output_path: Path,
    artifact_id: int,
    artifact_name: str,
    artifact_archive_sha256: str,
    page_url: str,
    public_url: str,
    release_tag: str | None = None,
) -> dict[str, Any]:
    _raw_bytes, raw = _load_bytes(raw_path)
    reconciliation_input_bytes, reconciliation_input = _load_bytes(
        reconciliation_input_path
    )
    proposals_bytes, proposals = _load_bytes(proposals_path)
    provider_outcomes_bytes, provider_outcomes = _load_bytes(provider_outcomes_path)
    public = build_public_online_memory_lineage(raw)
    public_bytes = (
        json.dumps(public, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    judge = json.loads(judge_path.read_bytes())
    reference = build_reference(
        raw,
        public,
        public_bytes=public_bytes,
        reconciliation_input_bytes=reconciliation_input_bytes,
        reconciliation_input=reconciliation_input,
        proposals_bytes=proposals_bytes,
        proposals=proposals,
        provider_outcomes_bytes=provider_outcomes_bytes,
        provider_outcomes=provider_outcomes,
        artifact_id=artifact_id,
        artifact_name=artifact_name,
        artifact_archive_sha256=artifact_archive_sha256,
        page_url=page_url,
        public_url=public_url,
    )
    judge["schema_version"] = 14
    judge["generated_at"] = raw["generated_at"]
    judge["claim_boundary"] = (
        "Read-only verification of one real-provider online memory-lineage pair: "
        "a successful provider receipt is promoted into CockroachDB, embedded by "
        "Titan, retrieved through a non-bypass RLS identity, admitted by a "
        "provider-attested causal contract, cited in a durable proposal, and "
        "joined to a later provider action and verified outcome. A cross-head "
        "reconciler completed the database lineage with zero provider redispatch. "
        "This is an architectural closure over one same-cause and one near-neighbor "
        "case, not a population-level superiority estimate."
    )
    judge["online_memory_lineage"] = reference
    if release_tag is not None:
        if not release_tag or any(character.isspace() for character in release_tag):
            raise RuntimeError("release tag is invalid")
        release = judge["release_envelope"]
        release["tag"] = release_tag
        release["release_url"] = (
            f"https://github.com/{raw['repository']}/releases/tag/{release_tag}"
        )
        release["release_api_url"] = (
            f"https://api.github.com/repos/{raw['repository']}/releases/tags/"
            f"{release_tag}"
        )
        release["online_memory_lineage_asset_name"] = (
            "online-memory-lineage-v1.json"
        )
        name_fields = {
            "asset_name": "asset_url",
            "sandbox_asset_name": "sandbox_asset_url",
            "ablation_asset_name": "ablation_asset_url",
            "drilldown_asset_name": "drilldown_asset_url",
            "guardian_asset_name": "guardian_asset_url",
            "replication_asset_name": "replication_asset_url",
            "blind_holdout_asset_name": "blind_holdout_asset_url",
            "sequential_blind_asset_name": "sequential_blind_asset_url",
            "evidence_story_asset_name": "evidence_story_asset_url",
            "ci_recovery_asset_name": "ci_recovery_asset_url",
            "adaptive_diagnosis_asset_name": "adaptive_diagnosis_asset_url",
            "transfer_firewall_asset_name": "transfer_firewall_asset_url",
            "online_memory_lineage_asset_name": (
                "online_memory_lineage_asset_url"
            ),
        }
        for name_field, url_field in name_fields.items():
            asset_name = release.get(name_field)
            if asset_name:
                release[url_field] = (
                    f"https://github.com/{raw['repository']}/releases/download/"
                    f"{release_tag}/{asset_name}"
                )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(public_bytes)
    judge_path.write_text(
        json.dumps(judge, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--reconciliation-input", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--provider-outcomes", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-archive-sha256", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--release-tag")
    args = parser.parse_args()
    print(
        json.dumps(
            promote(
                raw_path=args.raw,
                reconciliation_input_path=args.reconciliation_input,
                proposals_path=args.proposals,
                provider_outcomes_path=args.provider_outcomes,
                judge_path=args.judge,
                output_path=args.output,
                artifact_id=args.artifact_id,
                artifact_name=args.artifact_name,
                artifact_archive_sha256=args.artifact_archive_sha256,
                page_url=args.page_url,
                public_url=args.public_url,
                release_tag=args.release_tag,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

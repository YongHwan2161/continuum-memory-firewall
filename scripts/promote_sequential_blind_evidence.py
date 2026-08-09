"""Promote an exact sequential-blind artifact into public judge evidence."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from continuum.blind_holdout import canonical_json_bytes
from continuum.sequential_blind import build_public_sequential_blind
from scripts.judge_readonly_verify import verify_sequential_blind_campaign


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_NAME = "sequential-blind-v1.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    temporary.replace(path)


def promote(
    *,
    judge_path: Path,
    campaign_report_path: Path,
    public_output_path: Path,
    workflow_receipt_path: Path,
    artifact_receipt_path: Path,
    repository: str,
    release_tag: str,
) -> dict[str, Any]:
    judge = _load(judge_path)
    campaign = _load(campaign_report_path)
    workflow = _load(workflow_receipt_path)
    artifact = _load(artifact_receipt_path)
    public = build_public_sequential_blind(campaign)
    public_bytes = canonical_json_bytes(public)
    public_sha = hashlib.sha256(public_bytes).hexdigest()

    run_id = int(workflow.get("id", 0))
    run_attempt = int(workflow.get("run_attempt", 0))
    artifact_id = int(artifact.get("id", 0))
    source_head = str(workflow.get("head_sha", ""))
    artifact_digest = str(artifact.get("digest", "")).removeprefix("sha256:")
    expected_name = (
        f"continuum-sequential-blind-{source_head}-{run_id}-{run_attempt}"
    )
    if workflow.get("conclusion") != "success":
        raise RuntimeError("sequential workflow did not succeed")
    if SHA_PATTERN.fullmatch(source_head) is None:
        raise RuntimeError("workflow source head is invalid")
    if run_id < 1 or run_attempt < 1 or artifact_id < 1:
        raise RuntimeError("provider receipt identity is invalid")
    if artifact.get("name") != expected_name:
        raise RuntimeError("artifact name is not exact-run bound")
    if SHA256_PATTERN.fullmatch(artifact_digest) is None:
        raise RuntimeError("artifact archive digest is invalid")
    if artifact.get("expired") is not False:
        raise RuntimeError("artifact is expired")
    if int(artifact.get("workflow_run", {}).get("id", 0)) != run_id:
        raise RuntimeError("artifact workflow identity drifted")
    if public.get("source_head") != source_head:
        raise RuntimeError("campaign source head drifted")
    if public.get("aggregation_workflow") != {
        "run_id": run_id,
        "run_attempt": run_attempt,
    }:
        raise RuntimeError("campaign aggregation workflow drifted")

    base = f"https://github.com/{repository}"
    api = f"https://api.github.com/repos/{repository}"
    public_base = str(judge["public_demo"]["url"]).rstrip("/")
    reference = {
        "schema_version": 1,
        "head_sha": source_head,
        "workflow_run_id": run_id,
        "workflow_attempt": run_attempt,
        "workflow_url": f"{base}/actions/runs/{run_id}",
        "workflow_api_url": f"{api}/actions/runs/{run_id}",
        "artifact_id": artifact_id,
        "artifact_name": expected_name,
        "artifact_archive_sha256": artifact_digest,
        "artifact_api_url": f"{api}/actions/artifacts/{artifact_id}",
        "public_url": f"{public_base}/evidence/{PUBLIC_NAME}",
        "page_url": f"{public_base}/sequential-blind.html",
        "public_sha256": public_sha,
        "campaign_id": public["campaign_id"],
        "campaign_manifest_sha256": public["campaign_manifest"][
            "campaign_manifest_sha256"
        ],
        "campaign_seal_receipt_sha256": public["campaign_seal_receipt"][
            "receipt_sha256"
        ],
    }
    candidate = deepcopy(judge)
    candidate["schema_version"] = 9
    candidate["generated_at"] = public["generated_at"]
    candidate["sequential_blind_campaign"] = reference
    candidate["claim_boundary"] = (
        "Read-only verification of live identity-bound memory, a label-hidden "
        "three-batch sequential GitHub and S3 campaign with 540 provider "
        "observations, prior blind and time-cluster evidence, CockroachDB "
        "vector/RLS evidence, AWS receipts, an immutable release, and Devpost "
        "lineage. Sequential batches are time clusters, not independent people "
        "or calendar days."
    )
    release = candidate["release_envelope"]
    release["tag"] = release_tag
    release["release_url"] = f"{base}/releases/tag/{release_tag}"
    release["release_api_url"] = f"{api}/releases/tags/{release_tag}"
    for key, value in list(release.items()):
        if key.endswith("_asset_url") or key == "asset_url":
            name_key = "asset_name" if key == "asset_url" else key.replace(
                "_asset_url", "_asset_name"
            )
            asset_name = release.get(name_key)
            if asset_name:
                release[key] = f"{base}/releases/download/{release_tag}/{asset_name}"
    release["sequential_blind_asset_name"] = PUBLIC_NAME
    release["sequential_blind_asset_url"] = (
        f"{base}/releases/download/{release_tag}/{PUBLIC_NAME}"
    )

    def fetch_json(url: str) -> dict[str, Any]:
        if url == reference["workflow_api_url"]:
            return workflow
        if url == reference["artifact_api_url"]:
            return artifact
        raise RuntimeError(f"unexpected provider URL: {url}")

    if not verify_sequential_blind_campaign(
        candidate,
        fetch_json=fetch_json,
        fetch_bytes=lambda url: (
            public_bytes
            if url == reference["public_url"]
            else (_ for _ in ()).throw(RuntimeError(f"unexpected public URL: {url}"))
        ),
    ):
        raise RuntimeError("promoted sequential campaign failed judge verification")

    judge_bytes = (json.dumps(candidate, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    _atomic_write(public_output_path, public_bytes)
    _atomic_write(judge_path, judge_bytes)
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", type=Path, required=True)
    parser.add_argument("--campaign-report", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--workflow-receipt", type=Path, required=True)
    parser.add_argument("--artifact-receipt", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", default="hackathon-v14")
    args = parser.parse_args()
    promoted = promote(
        judge_path=args.judge,
        campaign_report_path=args.campaign_report,
        public_output_path=args.public_output,
        workflow_receipt_path=args.workflow_receipt,
        artifact_receipt_path=args.artifact_receipt,
        repository=args.repository,
        release_tag=args.release_tag,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": promoted["schema_version"],
                "workflow_run_id": promoted["sequential_blind_campaign"][
                    "workflow_run_id"
                ],
                "public_sha256": promoted["sequential_blind_campaign"][
                    "public_sha256"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

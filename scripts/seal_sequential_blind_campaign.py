"""Build and seal the complete three-batch manifest before candidates run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from continuum.blind_holdout import canonical_json_bytes, write_canonical_json
from continuum.sequential_blind import build_campaign_manifest
try:
    from scripts.seal_blind_holdout import _load, _seal_object, _write_private
except ModuleNotFoundError as exc:
    if exc.name != "scripts" and not str(exc.name).startswith("scripts."):
        raise
    from seal_blind_holdout import _load, _seal_object, _write_private  # type: ignore[no-redef]


def seal_campaign(
    *,
    client: Any,
    bucket: str,
    prefix: str,
    commitment_paths: list[Path],
    source_head: str,
    campaign_id: str,
    manifest_path: Path,
    receipt_path: Path,
    workflow_run_id: int,
    workflow_run_attempt: int,
) -> tuple[dict, dict]:
    commitments = [_load(path)[0] for path in commitment_paths]
    manifest = build_campaign_manifest(
        commitments=commitments,
        source_head=source_head,
        campaign_id=campaign_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    write_canonical_json(manifest_path, manifest)
    prefix = prefix.strip("/")
    manifest_object = _seal_object(
        client,
        bucket=bucket,
        key=f"{prefix}/campaign-{manifest['campaign_manifest_sha256']}.json",
        body=canonical_json_bytes(manifest),
        kind="sequential-blind-campaign-manifest",
    )
    receipt = {
        "schema_version": 1,
        "kind": "continuum.sequential-blind.campaign-seal-receipt",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "source_head": source_head,
        "campaign_id": campaign_id,
        "campaign_manifest_sha256": manifest["campaign_manifest_sha256"],
        "manifest_object": manifest_object,
        "commitment_sha256s": [
            item["commitment_sha256"]
            for item in sorted(commitments, key=lambda value: value["batch_index"])
        ],
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "write_once_condition": "If-None-Match:*",
        "server_side_encryption": "AES256",
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    _write_private(receipt_path, receipt)
    return manifest, receipt


def main() -> None:
    import boto3

    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--commitment", action="append", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    args = parser.parse_args()
    if len(args.commitment) != 3:
        raise SystemExit("exactly three --commitment inputs are required")
    manifest, receipt = seal_campaign(
        client=boto3.client("s3", region_name=args.region),
        bucket=args.bucket,
        prefix=args.prefix,
        commitment_paths=args.commitment,
        source_head=args.source_head,
        campaign_id=args.campaign_id,
        manifest_path=args.manifest_output,
        receipt_path=args.receipt_output,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    print(
        json.dumps(
            {
                "campaign_id": manifest["campaign_id"],
                "campaign_manifest_sha256": manifest["campaign_manifest_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "sealed_batches": len(manifest["batches"]),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

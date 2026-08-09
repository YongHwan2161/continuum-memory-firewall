"""Seal one sequential blind batch in content-addressed S3 objects."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from continuum.blind_holdout import canonical_json_bytes
from continuum.sequential_blind import validate_sequential_blind
from scripts.seal_blind_holdout import _load, _seal_object, _write_private


def seal_batch(
    *,
    client: Any,
    bucket: str,
    prefix: str,
    challenge_path: Path,
    labels_path: Path,
    commitment_path: Path,
    output_path: Path,
    workflow_run_id: int,
    workflow_run_attempt: int,
) -> dict:
    challenge, challenge_bytes = _load(challenge_path)
    labels, labels_bytes = _load(labels_path)
    commitment, commitment_bytes = _load(commitment_path)
    validate_sequential_blind(challenge, labels, commitment)
    prefix = prefix.strip("/")
    objects = {
        "challenge": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/challenge-{commitment['challenge_sha256']}.json",
            body=challenge_bytes,
            kind="sequential-blind-challenge",
        ),
        "labels": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/labels-{commitment['labels_sha256']}.json",
            body=labels_bytes,
            kind="sequential-blind-sealed-labels",
        ),
        "commitment": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/commitment-{commitment['commitment_sha256']}.json",
            body=commitment_bytes,
            kind="sequential-blind-commitment",
        ),
    }
    receipt = {
        "schema_version": 1,
        "kind": "continuum.sequential-blind.s3-seal-receipt",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "bucket_sha256": hashlib.sha256(bucket.encode()).hexdigest(),
        "prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "source_head": commitment["source_head"],
        "campaign_id": commitment["campaign_id"],
        "batch_index": commitment["batch_index"],
        "commitment_sha256": commitment["commitment_sha256"],
        "objects": objects,
        "write_once_condition": "If-None-Match:*",
        "server_side_encryption": "AES256",
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    _write_private(output_path, receipt)
    return receipt


def main() -> None:
    import boto3

    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    args = parser.parse_args()
    receipt = seal_batch(
        client=boto3.client("s3", region_name=args.region),
        bucket=args.bucket,
        prefix=args.prefix,
        challenge_path=args.challenge,
        labels_path=args.labels,
        commitment_path=args.commitment,
        output_path=args.output,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
    )
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()

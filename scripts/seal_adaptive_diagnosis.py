"""Seal adaptive-diagnosis challenge and labels in content-addressed S3."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from continuum.adaptive_diagnosis import validate_adaptive_diagnosis_inputs
from continuum.blind_holdout import canonical_json_bytes
from scripts.seal_blind_holdout import _seal_object, _write_private


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    canonical = canonical_json_bytes(value)
    if data.replace(b"\r\n", b"\n") != canonical:
        raise RuntimeError(f"{path.name} is not canonical JSON")
    return value, canonical


def seal(
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
) -> dict[str, Any]:
    challenge, challenge_bytes = _load(challenge_path)
    labels, labels_bytes = _load(labels_path)
    commitment, commitment_bytes = _load(commitment_path)
    validate_adaptive_diagnosis_inputs(challenge, labels, commitment)
    prefix = prefix.strip("/")
    objects = {
        "challenge": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/challenge-{commitment['challenge_sha256']}.json",
            body=challenge_bytes,
            kind="adaptive-diagnosis-challenge",
        ),
        "labels": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/labels-{commitment['labels_sha256']}.json",
            body=labels_bytes,
            kind="adaptive-diagnosis-sealed-labels",
        ),
        "commitment": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/commitment-{commitment['commitment_sha256']}.json",
            body=commitment_bytes,
            kind="adaptive-diagnosis-commitment",
        ),
    }
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "kind": "continuum.adaptive-diagnosis.s3-seal-receipt",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "bucket_sha256": hashlib.sha256(bucket.encode()).hexdigest(),
        "prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "source_head": commitment["source_head"],
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
    receipt = seal(
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

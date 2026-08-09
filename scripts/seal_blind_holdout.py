"""Seal content-addressed holdout inputs in private S3 before execution."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from continuum.blind_holdout import canonical_json_bytes, validate_blind_holdout


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    canonical = canonical_json_bytes(value)
    if data.replace(b"\r\n", b"\n") != canonical:
        raise RuntimeError(f"{path.name} is not canonical JSON")
    return value, canonical


def _write_private(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(dict(value)))
    os.chmod(path, 0o600)


def _seal_object(
    client: Any,
    *,
    bucket: str,
    key: str,
    body: bytes,
    kind: str,
) -> Mapping[str, Any]:
    sha256 = hashlib.sha256(body).hexdigest()
    try:
        response = client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
            ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode(),
            IfNoneMatch="*",
            Metadata={"continuum-kind": kind, "sha256": sha256},
        )
    except Exception as exc:
        # Keep the pure sealing contract testable without loading the AWS SDK.
        # At runtime boto3 raises ClientError, whose structured response is
        # checked narrowly before an existing content-addressed object is used.
        error_response = getattr(exc, "response", {})
        error = error_response.get("Error", {})
        status = error_response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status != 412 and error.get("Code") not in {"PreconditionFailed", "412"}:
            raise
        response = {}
    downloaded = client.get_object(Bucket=bucket, Key=key)
    actual = downloaded["Body"].read()
    if actual != body:
        raise RuntimeError(f"sealed S3 object changed at {key}")
    metadata = downloaded.get("Metadata", {})
    if metadata.get("sha256") != sha256:
        raise RuntimeError(f"sealed S3 metadata digest mismatch at {key}")
    return {
        "key": key,
        "sha256": sha256,
        "etag": str(downloaded.get("ETag", response.get("ETag", ""))).strip('"'),
        "version_id": downloaded.get("VersionId") or response.get("VersionId"),
        "server_side_encryption": downloaded.get("ServerSideEncryption", "AES256"),
    }


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
    validate_blind_holdout(challenge, labels, commitment)
    prefix = prefix.strip("/")
    objects = {
        "challenge": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/challenge-{commitment['challenge_sha256']}.json",
            body=challenge_bytes,
            kind="blind-holdout-challenge",
        ),
        "labels": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/labels-{commitment['labels_sha256']}.json",
            body=labels_bytes,
            kind="blind-holdout-sealed-labels",
        ),
        "commitment": _seal_object(
            client,
            bucket=bucket,
            key=f"{prefix}/commitment-{commitment['commitment_sha256']}.json",
            body=commitment_bytes,
            kind="blind-holdout-commitment",
        ),
    }
    receipt = {
        "schema_version": 1,
        "kind": "continuum.blind-holdout.s3-seal-receipt",
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
    receipt["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
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

"""Generate one label-separated batch for a preregistered sequential campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import boto3

from continuum.blind_holdout import canonical_json_bytes
from continuum.sequential_blind import generate_sequential_blind_batch


def _write_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(value))
    os.chmod(path, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--model-id", default="amazon.nova-micro-v1:0")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--generation-nonce", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    challenge, labels, commitment = generate_sequential_blind_batch(
        client=boto3.client("bedrock-runtime", region_name=args.region),
        model_id=args.model_id,
        source_head=args.source_head,
        campaign_id=args.campaign_id,
        batch_index=args.batch_index,
        generation_nonce=args.generation_nonce,
    )
    _write_private(args.output_dir / "challenge.json", challenge)
    _write_private(args.output_dir / "labels.json", labels)
    _write_private(args.output_dir / "commitment.json", commitment)
    print(
        json.dumps(
            {
                "batch_index": args.batch_index,
                "campaign_id": args.campaign_id,
                "case_count": challenge["case_count"],
                "challenge_sha256": commitment["challenge_sha256"],
                "commitment_sha256": commitment["commitment_sha256"],
                "labels_sha256": commitment["labels_sha256"],
                "scoring_policy_sha256": commitment["scoring_policy_sha256"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

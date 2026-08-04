"""Call the real AWS sandbox adapter twice and prove one durable effect."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from continuum.aws_sandbox_provider import AwsLambdaSandboxProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    provider = AwsLambdaSandboxProvider(
        function_name=args.function_name,
        region=args.region,
    )
    idempotency_key = str(uuid4())
    action_payload = {
        "action_key": "sandbox:inspect:proof-v1",
        "action_type": "inspect_service",
        "parameters": {"service": "checkout"},
        "schema_version": 1,
    }
    first = provider.send(
        action_payload=action_payload,
        idempotency_key=idempotency_key,
    )
    replay = provider.send(
        action_payload=action_payload,
        idempotency_key=idempotency_key,
    )
    lookup = provider.lookup(idempotency_key=idempotency_key)
    if lookup is None:
        raise RuntimeError("sandbox receipt lookup returned no outcome")
    receipts = {
        first.provider_receipt_id,
        replay.provider_receipt_id,
        lookup.provider_receipt_id,
    }
    effect_counts = {
        first.evidence.get("effect_count"),
        replay.evidence.get("effect_count"),
        lookup.evidence.get("effect_count"),
    }
    if len(receipts) != 1 or effect_counts != {1}:
        raise RuntimeError("sandbox idempotency or receipt lookup invariant failed")
    report = {
        "schema_version": 1,
        "source_head": args.source_head,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider.name,
        "provider_capabilities": provider.capabilities.as_evidence(),
        "receipt_id_sha256": hashlib.sha256(
            str(first.provider_receipt_id).encode("utf-8")
        ).hexdigest(),
        "send_count": 2,
        "logical_effect_count": 1,
        "receipt_lookup_matched": True,
        "gate": {
            "idempotency": "PASS",
            "receipt_lookup": "PASS",
            "sandbox_only": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

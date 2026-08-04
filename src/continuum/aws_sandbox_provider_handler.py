"""Lambda handler for the durable, non-production action-effect sandbox."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Any, Mapping

import boto3
from botocore.exceptions import ClientError


TABLE_NAME = os.environ["CONTINUUM_SANDBOX_RECEIPT_TABLE"]
TABLE = boto3.resource("dynamodb").Table(TABLE_NAME)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _stored_outcome(idempotency_key: str) -> Mapping[str, Any] | None:
    result = TABLE.get_item(
        Key={"idempotency_key": idempotency_key},
        ConsistentRead=True,
    )
    item = result.get("Item")
    if not isinstance(item, Mapping):
        return None
    value = json.loads(str(item["outcome_json"]))
    if not isinstance(value, Mapping):
        raise RuntimeError("stored sandbox receipt is invalid")
    return value


def _send(event: Mapping[str, Any]) -> Mapping[str, Any]:
    provider = str(event.get("provider", ""))
    idempotency_key = str(event.get("idempotency_key", ""))
    action_payload = event.get("action_payload")
    if (
        provider != "continuum-aws-sandbox-v1"
        or not idempotency_key
        or len(idempotency_key) > 256
        or not isinstance(action_payload, Mapping)
    ):
        raise ValueError("sandbox send contract is invalid")
    payload_digest = hashlib.sha256(_canonical(action_payload)).hexdigest()
    receipt_digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    observed_at = datetime.now(timezone.utc)
    outcome = {
        "provider": provider,
        "status": "succeeded",
        "provider_receipt_id": f"sandbox-{receipt_digest[:32]}",
        "evidence": {
            "action_payload_sha256": payload_digest,
            "effect_count": 1,
            "sandbox": True,
            "schema_version": 1,
        },
        "observed_at": observed_at.isoformat(),
        "verified_at": observed_at.isoformat(),
    }
    try:
        TABLE.put_item(
            Item={
                "idempotency_key": idempotency_key,
                "outcome_json": json.dumps(
                    outcome,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "expires_at": int((observed_at + timedelta(days=1)).timestamp()),
            },
            ConditionExpression="attribute_not_exists(idempotency_key)",
        )
        return outcome
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        prior = _stored_outcome(idempotency_key)
        if prior is None:
            raise RuntimeError("sandbox receipt disappeared after conditional write")
        if prior.get("evidence", {}).get("action_payload_sha256") != payload_digest:
            raise RuntimeError("idempotency key was reused with a different payload")
        return prior


def handler(event: object, context: object) -> Mapping[str, Any]:
    del context
    if not isinstance(event, Mapping):
        raise ValueError("sandbox event must be an object")
    operation = event.get("operation")
    if operation == "send":
        outcome = _send(event)
    elif operation == "lookup":
        key = str(event.get("idempotency_key", ""))
        if not key or len(key) > 256:
            raise ValueError("sandbox lookup contract is invalid")
        outcome = _stored_outcome(key)
    else:
        raise ValueError("sandbox operation is not allowlisted")
    return {"schema_version": 1, "outcome": outcome}

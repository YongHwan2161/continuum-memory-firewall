"""Disposable S3 object-state provider for the blind real-effect holdout."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Any, Mapping

from continuum.episode import OutcomeStatus, ProposedAction, ProviderOutcome, RiskClass
from continuum.orchestrator import ActionPolicy
from continuum.outbox import ProviderCapabilityManifest
from continuum.release_guardian import ReleaseGuardianCase


MARKER_NAME = "sandbox-marker.json"
PAYLOAD_NAME = "payload.json"
RECEIPT_NAME = "reconciliation-receipt.json"
QUARANTINED_NAME = "quarantined-payload.json"
MARKER_BODY = b'{"kind":"continuum.s3-holdout-marker"}\n'
PAYLOAD_BODY = b'{"kind":"continuum.s3-holdout","value":"expected"}\n'
CONFLICT_BODY = b'{"kind":"continuum.s3-holdout","value":"conflict"}\n'
RECEIPT_BODY = b'{"kind":"continuum.s3-holdout-receipt","status":"verified"}\n'


S3_ACTION_POLICIES: Mapping[str, ActionPolicy] = {
    action_type: ActionPolicy(
        action_type=action_type,
        risk_class=RiskClass.REVERSIBLE,
        parameter_properties={},
    )
    for action_type in (
        "create_sandbox_marker",
        "upload_sandbox_payload",
        "adopt_existing_s3_payload",
        "upload_s3_reconciliation_receipt",
        "quarantine_conflicting_s3_object",
        "delete_sandbox_prefix",
    )
}


class S3ObjectSandboxProvider:
    name = "s3-object-disposable-sandbox-v1"
    capability_manifest = ProviderCapabilityManifest(
        supports_idempotency=True,
        receipt_lookup=True,
        reconciliation_timeout=timedelta(seconds=30),
    )

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        run_namespace: str,
        base_prefix: str = "blind-holdout-sandbox",
    ) -> None:
        if not bucket:
            raise ValueError("S3 bucket is required")
        if not re.fullmatch(r"[A-Za-z0-9._-]{8,180}", run_namespace):
            raise ValueError("run_namespace is not bounded")
        self.client = client
        self.bucket = bucket
        self.run_namespace = run_namespace
        self.base_prefix = base_prefix.strip("/")
        self._prefixes: dict[str, str] = {}
        self._receipts: dict[str, ProviderOutcome] = {}
        self._effects: dict[str, int] = {}

    def _prefix(self, arm: str, case_id: str) -> str:
        safe_arm = re.sub(r"[^a-z0-9-]", "-", arm.lower())
        safe_case = re.sub(r"[^a-z0-9-]", "-", case_id.lower())
        return f"{self.base_prefix}/{self.run_namespace}/{safe_arm}/{safe_case}/"

    def _key(self, prefix: str, name: str) -> str:
        return prefix + name

    def _put(self, prefix: str, name: str, body: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(prefix, name),
            Body=body,
            ServerSideEncryption="AES256",
            ContentType="application/json",
            Metadata={"sha256": hashlib.sha256(body).hexdigest()},
        )

    def _delete_prefix(self, prefix: str) -> int:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        objects = [
            {"Key": item["Key"]}
            for item in response.get("Contents", [])
            if isinstance(item, Mapping) and isinstance(item.get("Key"), str)
        ]
        if not objects:
            return 0
        self.client.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": objects, "Quiet": True},
        )
        return len(objects)

    def _state(self, prefix: str) -> Mapping[str, Any]:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        objects: list[dict[str, Any]] = []
        for item in response.get("Contents", []):
            key = item.get("Key")
            if not isinstance(key, str):
                continue
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            objects.append(
                {
                    "name": key.removeprefix(prefix),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "size": len(body),
                }
            )
        return {"objects": sorted(objects, key=lambda value: value["name"])}

    def prepare(self, *, arm: str, case: ReleaseGuardianCase) -> Mapping[str, Any]:
        return self.prepare_fixture(
            arm=arm, case_id=case.case_id, fixture=case.family
        )

    def prepare_fixture(
        self, *, arm: str, case_id: str, fixture: str
    ) -> Mapping[str, Any]:
        prefix = self._prefix(arm, case_id)
        self._delete_prefix(prefix)
        if fixture == "missing-prefix":
            pass
        elif fixture == "missing-payload":
            self._put(prefix, MARKER_NAME, MARKER_BODY)
        elif fixture == "lost-payload-ack":
            self._put(prefix, MARKER_NAME, MARKER_BODY)
            self._put(prefix, PAYLOAD_NAME, PAYLOAD_BODY)
        elif fixture == "missing-s3-receipt":
            self._put(prefix, MARKER_NAME, MARKER_BODY)
            self._put(prefix, PAYLOAD_NAME, PAYLOAD_BODY)
        elif fixture == "conflicting-s3-payload":
            self._put(prefix, MARKER_NAME, MARKER_BODY)
            self._put(prefix, PAYLOAD_NAME, CONFLICT_BODY)
        elif fixture == "s3-cleanup-pending":
            self._put(prefix, MARKER_NAME, MARKER_BODY)
            self._put(prefix, PAYLOAD_NAME, PAYLOAD_BODY)
            self._put(prefix, RECEIPT_NAME, RECEIPT_BODY)
        else:
            raise RuntimeError(f"unsupported S3 holdout fixture: {fixture}")
        self._prefixes[case_id] = prefix
        return self._state(prefix)

    def execute(
        self,
        *,
        case: ReleaseGuardianCase,
        proposal: ProposedAction,
        idempotency_key: str,
        observed_at: datetime,
    ) -> ProviderOutcome:
        prior = self._receipts.get(idempotency_key)
        if prior is not None:
            return prior
        prefix = self._prefixes.get(case.case_id)
        if prefix is None:
            raise RuntimeError("S3 sandbox was not prepared")
        before = self._state(prefix)
        matched = proposal.action_type == case.expected_action_type
        effect_count = 0
        if matched:
            if proposal.action_type == "create_sandbox_marker":
                self._put(prefix, MARKER_NAME, MARKER_BODY)
                effect_count = 1
            elif proposal.action_type == "upload_sandbox_payload":
                self._put(prefix, PAYLOAD_NAME, PAYLOAD_BODY)
                effect_count = 1
            elif proposal.action_type == "adopt_existing_s3_payload":
                pass
            elif proposal.action_type == "upload_s3_reconciliation_receipt":
                self._put(prefix, RECEIPT_NAME, RECEIPT_BODY)
                effect_count = 1
            elif proposal.action_type == "quarantine_conflicting_s3_object":
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=self._key(prefix, QUARANTINED_NAME),
                    CopySource={"Bucket": self.bucket, "Key": self._key(prefix, PAYLOAD_NAME)},
                    ServerSideEncryption="AES256",
                    MetadataDirective="COPY",
                )
                self.client.delete_object(Bucket=self.bucket, Key=self._key(prefix, PAYLOAD_NAME))
                effect_count = 1
            elif proposal.action_type == "delete_sandbox_prefix":
                self._delete_prefix(prefix)
                # One proposal owns one logical provider transition even when
                # the bounded prefix contains several physical objects.
                effect_count = 1
            else:
                matched = False
        after = self._state(prefix)
        succeeded = matched and self._verify(case.expected_action_type, after)
        state_digest = hashlib.sha256(
            json.dumps(after, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        prefix_digest = hashlib.sha256(prefix.encode()).hexdigest()
        outcome = ProviderOutcome(
            provider=self.name,
            status=OutcomeStatus.SUCCEEDED if succeeded else OutcomeStatus.FAILED,
            evidence={
                "case_id": case.case_id,
                "expected_action_type": case.expected_action_type,
                "proposed_action_type": proposal.action_type,
                "action_match": proposal.action_type == case.expected_action_type,
                "provider_state_verified": succeeded,
                "before_state_sha256": hashlib.sha256(
                    json.dumps(before, separators=(",", ":"), sort_keys=True).encode()
                ).hexdigest(),
                "after_state_sha256": state_digest,
                "effect_count": effect_count,
                "prefix_sha256": prefix_digest,
                "capability_manifest": self.capability_manifest.as_evidence(),
                "sandbox_only": True,
            },
            observed_at=observed_at,
            provider_receipt_id=(
                f"s3-object:{prefix_digest}:{state_digest}" if succeeded else None
            ),
            verified_at=observed_at if succeeded else None,
        )
        self._receipts[idempotency_key] = outcome
        self._effects[idempotency_key] = effect_count
        return outcome

    def execute_observed(
        self,
        *,
        case_id: str,
        proposal: ProposedAction,
        idempotency_key: str,
        observed_at: datetime,
    ) -> ProviderOutcome:
        """Execute and verify a proposed S3 transition without opening labels."""

        prior = self._receipts.get(idempotency_key)
        if prior is not None:
            return prior
        prefix = self._prefixes.get(case_id)
        if prefix is None:
            raise RuntimeError("S3 sandbox was not prepared")
        before = self._state(prefix)
        action_type = proposal.action_type
        effect_count = 0
        execution_error = None
        try:
            if action_type == "create_sandbox_marker":
                self._put(prefix, MARKER_NAME, MARKER_BODY)
                effect_count = 1
            elif action_type == "upload_sandbox_payload":
                self._put(prefix, PAYLOAD_NAME, PAYLOAD_BODY)
                effect_count = 1
            elif action_type == "adopt_existing_s3_payload":
                pass
            elif action_type == "upload_s3_reconciliation_receipt":
                self._put(prefix, RECEIPT_NAME, RECEIPT_BODY)
                effect_count = 1
            elif action_type == "quarantine_conflicting_s3_object":
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=self._key(prefix, QUARANTINED_NAME),
                    CopySource={"Bucket": self.bucket, "Key": self._key(prefix, PAYLOAD_NAME)},
                    ServerSideEncryption="AES256",
                    MetadataDirective="COPY",
                )
                self.client.delete_object(
                    Bucket=self.bucket, Key=self._key(prefix, PAYLOAD_NAME)
                )
                effect_count = 1
            elif action_type == "delete_sandbox_prefix":
                self._delete_prefix(prefix)
                effect_count = 1
            else:
                execution_error = "ACTION_NOT_ALLOWLISTED"
        except Exception as exc:
            # The trace retains only the error class. Credentials, object keys,
            # and provider response bodies never enter evaluation artifacts.
            execution_error = type(exc).__name__
        after = self._state(prefix)
        succeeded = execution_error is None and self._verify(action_type, after)
        state_digest = hashlib.sha256(
            json.dumps(after, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        prefix_digest = hashlib.sha256(prefix.encode()).hexdigest()
        outcome = ProviderOutcome(
            provider=self.name,
            status=OutcomeStatus.SUCCEEDED if succeeded else OutcomeStatus.FAILED,
            evidence={
                "case_id": case_id,
                "executed_action_type": action_type,
                "provider_state_verified": succeeded,
                "before_state_sha256": hashlib.sha256(
                    json.dumps(before, separators=(",", ":"), sort_keys=True).encode()
                ).hexdigest(),
                "after_state_sha256": state_digest,
                "effect_count": effect_count,
                "execution_error": execution_error,
                "prefix_sha256": prefix_digest,
                "capability_manifest": self.capability_manifest.as_evidence(),
                "evaluation_label_accessed": False,
                "sandbox_only": True,
            },
            observed_at=observed_at,
            provider_receipt_id=(
                f"s3-object:{prefix_digest}:{state_digest}" if succeeded else None
            ),
            verified_at=observed_at if succeeded else None,
        )
        self._receipts[idempotency_key] = outcome
        self._effects[idempotency_key] = effect_count
        return outcome

    @staticmethod
    def _verify(action_type: str, state: Mapping[str, Any]) -> bool:
        objects = {item["name"]: item for item in state.get("objects", [])}
        expected_payload = hashlib.sha256(PAYLOAD_BODY).hexdigest()
        if action_type == "create_sandbox_marker":
            return MARKER_NAME in objects
        if action_type == "upload_sandbox_payload":
            return objects.get(PAYLOAD_NAME, {}).get("sha256") == expected_payload
        if action_type == "adopt_existing_s3_payload":
            return objects.get(PAYLOAD_NAME, {}).get("sha256") == expected_payload
        if action_type == "upload_s3_reconciliation_receipt":
            return RECEIPT_NAME in objects
        if action_type == "quarantine_conflicting_s3_object":
            return PAYLOAD_NAME not in objects and QUARANTINED_NAME in objects
        if action_type == "delete_sandbox_prefix":
            return not objects
        return False

    def effect_count(self, idempotency_key: str) -> int:
        return self._effects.get(idempotency_key, 0)

    def cleanup(self, case_id: str) -> Mapping[str, int]:
        prefix = self._prefixes.get(case_id)
        if prefix is None:
            return {"deleted_count": 0, "residual_count": 0}
        deleted = self._delete_prefix(prefix)
        residual = len(self._state(prefix).get("objects", []))
        return {"deleted_count": deleted, "residual_count": residual}

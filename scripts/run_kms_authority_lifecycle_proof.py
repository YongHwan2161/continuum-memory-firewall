#!/usr/bin/env python3
"""Run the three-phase S3 -> KMS -> CockroachDB authority lifecycle proof."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

import boto3
from botocore.exceptions import ClientError

from continuum.aws_secrets import get_secret_string_with_backoff
from continuum.episode import (
    AgentArm,
    CockroachEpisodeStore,
    OutcomeStatus,
    ProposedAction,
    ProviderOutcome,
    RiskClass,
)
from continuum.kms_authority_proof import seal_kms_authority_proof
from continuum.kms_outcome_authority import (
    GENESIS_DIGEST,
    KMS_KEY_SPEC,
    KMS_SIGNING_ALGORITHM,
    KmsProviderOutcomeAttestationSigner,
    PinnedPublicKeyringVerifier,
    PublicVerificationKeyring,
    VerificationKeyState,
)
from continuum.migrate import Migrator
from continuum.outbox import CockroachOutboxStore, ProviderCapabilityManifest
from continuum.outcome_attestation import (
    OUTCOME_ATTESTATION_EXPIRED,
    OUTCOME_ATTESTATION_INVALID,
    OutcomeAttestationError,
    _canonical_bytes,
    _decode,
    _encode,
    handle_digest,
)
from continuum.scope_roles import configure_scope_read_policies, verify_scope_role
from continuum.store import pin_database_tls_root, psycopg_connection_factory
from continuum.tenant_control import DatabaseTenantControlPlane


ISSUER = "s3-provider-origin-verifier-kms-v2"
POLICY_VERSION = "s3-receipt-lookup-kms-v2"
PRIVATE_REQUEST_KIND = "continuum.kms-authority.private-request"
PRIVATE_ISSUANCE_KIND = "continuum.kms-authority.private-issuance"


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _write_private(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o600)


def _write_public(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _load_s3_json(client: Any, *, bucket: str, key: str) -> dict[str, Any]:
    response = client.get_object(Bucket=bucket, Key=key)
    value = json.loads(response["Body"].read())
    if not isinstance(value, dict):
        raise RuntimeError("private handoff must be a JSON object")
    return value


def _put_s3_json(
    client: Any,
    *,
    bucket: str,
    key: str,
    value: Mapping[str, Any],
    source_head: str,
) -> None:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=_canonical_bytes(value) + b"\n",
        ContentType="application/json",
        ServerSideEncryption="AES256",
        Metadata={"continuum-source-head": source_head, "continuum-private": "true"},
    )


def _secret_payload(client: Any, secret_id: str) -> Any:
    raw = get_secret_string_with_backoff(client, secret_id)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _database_url(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Mapping) and isinstance(value.get("database_url"), str):
        return str(value["database_url"])
    raise RuntimeError("database secret does not contain database_url")


def _runtime_context(
    *,
    secret_client: Any,
    runtime_secret_id: str,
    ca_cert: str,
) -> tuple[str, str, str, str]:
    payload = _secret_payload(secret_client, runtime_secret_id)
    if not isinstance(payload, Mapping):
        raise RuntimeError("runtime secret must be a JSON object")
    callers = payload.get("caller_scopes")
    control_url = payload.get("control_plane_database_url")
    scope_urls = payload.get("scope_database_urls")
    if not isinstance(callers, Mapping) or len(callers) != 1:
        raise RuntimeError("proof requires exactly one registered demo caller")
    if not isinstance(control_url, str) or not isinstance(scope_urls, Mapping):
        raise RuntimeError("audited runtime database registry is incomplete")
    caller_id = str(next(iter(callers)))
    control_url = pin_database_tls_root(control_url, ca_cert)
    identity = DatabaseTenantControlPlane(
        psycopg_connection_factory(control_url)
    ).resolve(caller_id)
    runtime_url = scope_urls.get(identity.sql_role)
    if not isinstance(runtime_url, str):
        raise RuntimeError("resolved SQL role has no runtime connection")
    return (
        pin_database_tls_root(runtime_url, ca_cert),
        identity.tenant_id,
        identity.incident_id,
        identity.sql_role,
    )


def _put_provider_object(
    client: Any,
    *,
    bucket: str,
    key: str,
    source_head: str,
    epoch: int,
) -> None:
    body = _canonical_bytes(
        {
            "authority_epoch": epoch,
            "kind": "continuum.kms-authority.provider-object",
            "source_head": source_head,
        }
    ) + b"\n"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="AES256",
        Metadata={"continuum-source-head": source_head},
    )


S3_CAPABILITIES = ProviderCapabilityManifest(
    supports_idempotency=True,
    receipt_lookup=True,
    reconciliation_timeout=timedelta(seconds=0),
)


def _approved_proposal(
    *,
    episodes: CockroachEpisodeStore,
    outbox: CockroachOutboxStore,
    tenant_id: str,
    incident_id: str,
    workflow_run_id: int,
    epoch: int,
) -> tuple[str, str]:
    run = episodes.start_run(
        tenant_id=tenant_id,
        incident_id=incident_id,
        arm=AgentArm.CONTINUUM,
        model_id="kms-outcome-authority-lifecycle-v1",
        input_payload={"authority_epoch": epoch, "workflow_run_id": workflow_run_id},
    )
    proposal_id = episodes.record_proposal(
        run=run,
        proposal=ProposedAction(
            action_key=f"kms-authority:{workflow_run_id}:epoch-{epoch}",
            action_type="put_disposable_evidence_object",
            parameters={"authority_epoch": epoch, "provider": "aws-s3"},
            rationale="Bind a real provider receipt to one KMS authority epoch.",
            citation_memory_ids=(),
            risk_class=RiskClass.REVERSIBLE,
        ),
    )
    episodes.approve_proposal(
        proposal_id=proposal_id,
        actor="policy:kms-outcome-authority-lifecycle-v1",
        reason="checksum-addressed disposable evidence prefix only",
    )
    item = outbox.enqueue_proposal(
        proposal_id=proposal_id,
        provider="aws-s3",
        provider_capabilities=S3_CAPABILITIES,
    )
    return proposal_id, item.idempotency_key


class S3ReceiptLookupProvider:
    name = "aws-s3"

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        source_head: str,
        workflow_run_id: int,
        bindings: Mapping[str, str],
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.source_head = source_head
        self.workflow_run_id = workflow_run_id
        self.bindings = dict(bindings)
        self.lookup_count = 0

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None:
        key = self.bindings.get(idempotency_key)
        if key is None:
            return None
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read()
        if head.get("Metadata", {}).get("continuum-source-head") != self.source_head:
            raise RuntimeError("S3 provider source identity drifted")
        if int(head["ContentLength"]) != len(body):
            raise RuntimeError("S3 provider object changed between HEAD and GET")
        etag = str(head["ETag"]).strip('"')
        version_id = str(head.get("VersionId") or "unversioned")
        observed_at = head["LastModified"]
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        self.lookup_count += 1
        return ProviderOutcome(
            provider=self.name,
            status=OutcomeStatus.SUCCEEDED,
            provider_receipt_id="aws-s3:"
            + _sha256(f"{self.bucket}\x00{key}\x00{etag}\x00{version_id}"),
            evidence={
                "content_length": len(body),
                "etag_sha256": _sha256(etag),
                "object_key_sha256": _sha256(key),
                "object_sha256": _sha256(body),
                "provider_lookup": "s3:HeadObject+GetObject",
                "source_head": self.source_head,
                "version_id_sha256": _sha256(version_id),
                "workflow_run_id": self.workflow_run_id,
            },
            observed_at=observed_at,
            verified_at=datetime.now(timezone.utc),
        )


def _serialize_outcome(outcome: ProviderOutcome) -> dict[str, Any]:
    return {
        "evidence": dict(outcome.evidence),
        "observed_at": outcome.observed_at.isoformat(),
        "provider": outcome.provider,
        "provider_receipt_id": outcome.provider_receipt_id,
        "status": outcome.status.value,
        "verified_at": outcome.verified_at.isoformat() if outcome.verified_at else None,
    }


def _deserialize_outcome(value: Mapping[str, Any]) -> ProviderOutcome:
    if value.get("status") != "succeeded" or not isinstance(value.get("evidence"), Mapping):
        raise RuntimeError("private outcome contract is invalid")
    verified = value.get("verified_at")
    return ProviderOutcome(
        provider=str(value["provider"]),
        status=OutcomeStatus.SUCCEEDED,
        provider_receipt_id=str(value["provider_receipt_id"]),
        evidence=dict(value["evidence"]),
        observed_at=datetime.fromisoformat(str(value["observed_at"])),
        verified_at=datetime.fromisoformat(str(verified)) if verified else None,
    )


def _validate_common(args: argparse.Namespace) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("source-head must be a full lowercase commit")
    expected_prefix = (
        f"evidence/kms-authority/{args.source_head}/"
        f"{args.workflow_run_id}-{args.workflow_run_attempt}"
    )
    if args.prefix != expected_prefix:
        raise ValueError("KMS authority prefix is not checksum-addressed")


def prepare(args: argparse.Namespace) -> None:
    _validate_common(args)
    secrets_client = boto3.client("secretsmanager", region_name=args.region)
    s3 = boto3.client("s3", region_name=args.region)
    kms = boto3.client("kms", region_name=args.region)
    sts = boto3.client("sts", region_name=args.region)
    migrator_url = pin_database_tls_root(
        _database_url(_secret_payload(secrets_client, args.migrator_secret_id)),
        args.ca_cert,
    )
    runtime_url, tenant_id, incident_id, sql_role = _runtime_context(
        secret_client=secrets_client,
        runtime_secret_id=args.runtime_secret_id,
        ca_cert=args.ca_cert,
    )
    connect = psycopg_connection_factory(migrator_url)
    migration = Migrator(connect).migrate()
    configure_scope_read_policies(
        migrator_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )
    episodes = CockroachEpisodeStore(connect)
    outbox = CockroachOutboxStore(connect)
    cases: list[dict[str, Any]] = []
    for epoch, slot in ((1, "A"), (2, "B"), (3, "A")):
        proposal_id, idempotency_key = _approved_proposal(
            episodes=episodes,
            outbox=outbox,
            tenant_id=tenant_id,
            incident_id=incident_id,
            workflow_run_id=args.workflow_run_id,
            epoch=epoch,
        )
        object_key = f"{args.prefix}/provider/epoch-{epoch}.json"
        _put_provider_object(
            s3,
            bucket=args.bucket,
            key=object_key,
            source_head=args.source_head,
            epoch=epoch,
        )
        cases.append(
            {
                "authority_epoch": epoch,
                "idempotency_key": idempotency_key,
                "key_slot": slot,
                "object_key": object_key,
                "proposal_id": proposal_id,
            }
        )
    try:
        kms.sign(
            KeyId=args.key_a_arn,
            Message=b"continuum-action-worker-negative-iam-proof",
            MessageType="RAW",
            SigningAlgorithm=KMS_SIGNING_ALGORITHM,
        )
    except ClientError as error:
        raw_code = str(error.response.get("Error", {}).get("Code", ""))
        if "AccessDenied" not in raw_code:
            raise
        worker_kms_error_code = "AccessDenied"
    else:
        raise RuntimeError("action worker unexpectedly called kms:Sign")
    worker_arn = str(sts.get_caller_identity()["Arn"])
    request = {
        "action_worker": {
            "arn_sha256": _sha256(worker_arn),
            "kms_sign_denied": True,
            "kms_sign_error_code": worker_kms_error_code,
        },
        "cases": cases,
        "database": {
            "migration_version": migration.current_version,
            "sql_role_sha256": _sha256(sql_role),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "key_arns": {"A": args.key_a_arn, "B": args.key_b_arn},
        "kind": PRIVATE_REQUEST_KIND,
        "schema_version": 1,
        "source": {
            "deployment_artifact_sha256": args.deployment_artifact_sha256,
            "head": args.source_head,
            "workflow_run_attempt": args.workflow_run_attempt,
            "workflow_run_id": args.workflow_run_id,
        },
    }
    _write_private(args.output, request)
    print(json.dumps({"ok": True, "phase": "prepare", "proposal_count": 3}))


def issue(args: argparse.Namespace) -> None:
    _validate_common(args)
    s3 = boto3.client("s3", region_name=args.region)
    kms = boto3.client("kms", region_name=args.region)
    sts = boto3.client("sts", region_name=args.region)
    request = _load_s3_json(s3, bucket=args.bucket, key=args.request_key)
    if request.get("kind") != PRIVATE_REQUEST_KIND or request.get("schema_version") != 1:
        raise RuntimeError("private request contract is invalid")
    if request.get("source", {}).get("head") != args.source_head:
        raise RuntimeError("private request source identity drifted")
    key_arns = request.get("key_arns")
    cases = request.get("cases")
    if not isinstance(key_arns, Mapping) or not isinstance(cases, list) or len(cases) != 3:
        raise RuntimeError("private request authority plan is invalid")
    response_a = kms.get_public_key(KeyId=str(key_arns["A"]))
    response_b = kms.get_public_key(KeyId=str(key_arns["B"]))
    signers = {
        1: KmsProviderOutcomeAttestationSigner(
            kms,
            key_arn=str(key_arns["A"]),
            authority_epoch=1,
            issuer=ISSUER,
            public_key_response=response_a,
        ),
        2: KmsProviderOutcomeAttestationSigner(
            kms,
            key_arn=str(key_arns["B"]),
            authority_epoch=2,
            issuer=ISSUER,
            public_key_response=response_b,
        ),
        3: KmsProviderOutcomeAttestationSigner(
            kms,
            key_arn=str(key_arns["A"]),
            authority_epoch=3,
            issuer=ISSUER,
            public_key_response=response_a,
        ),
    }
    bindings = {
        str(case["idempotency_key"]): str(case["object_key"]) for case in cases
    }
    provider = S3ReceiptLookupProvider(
        client=s3,
        bucket=args.bucket,
        source_head=args.source_head,
        workflow_run_id=args.workflow_run_id,
        bindings=bindings,
    )
    issued: list[dict[str, Any]] = []
    issued_times: dict[int, datetime] = {}
    rotation_time: datetime | None = None
    rollback_time: datetime | None = None
    for case in cases:
        epoch = int(case["authority_epoch"])
        if epoch == 2:
            rotation_time = datetime.now(timezone.utc)
        elif epoch == 3:
            rollback_time = datetime.now(timezone.utc)
        issued_at = datetime.now(timezone.utc)
        outcome, raw_handle = signers[epoch].verify_and_issue(
            proposal_id=str(case["proposal_id"]),
            idempotency_key=str(case["idempotency_key"]),
            provider=provider,
            policy_version=POLICY_VERSION,
            issued_at=issued_at,
        )
        issued_times[epoch] = issued_at
        issued.append(
            {
                "authority_epoch": epoch,
                "handle": raw_handle,
                "handle_sha256": handle_digest(raw_handle),
                "outcome": _serialize_outcome(outcome),
                "proposal_id": str(case["proposal_id"]),
            }
        )
    if rotation_time is None or rollback_time is None:
        raise RuntimeError("rotation timeline was not created")
    first_case = cases[0]
    expired_outcome, expired_handle = signers[1].verify_and_issue(
        proposal_id=str(first_case["proposal_id"]),
        idempotency_key=str(first_case["idempotency_key"]),
        provider=provider,
        policy_version=POLICY_VERSION,
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    del expired_outcome
    activation_time = issued_times[1] - timedelta(minutes=1)
    verify_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    v1 = PublicVerificationKeyring.build(
        version=1,
        previous_manifest_sha256=GENESIS_DIGEST,
        transition="ACTIVATE_KEY_A",
        effective_at=activation_time,
        entries=(
            signers[1].verification_key(
                state=VerificationKeyState.ACTIVE,
                signing_not_before=activation_time,
            ),
        ),
    )
    v2 = PublicVerificationKeyring.build(
        version=2,
        previous_manifest_sha256=v1.manifest_sha256,
        transition="ROTATE_TO_KEY_B",
        effective_at=rotation_time,
        entries=(
            signers[1].verification_key(
                state=VerificationKeyState.RETIRING,
                signing_not_before=activation_time,
                signing_not_after=rotation_time,
                verify_until=verify_until,
            ),
            signers[2].verification_key(
                state=VerificationKeyState.ACTIVE,
                signing_not_before=rotation_time,
            ),
        ),
    )
    v3 = PublicVerificationKeyring.build(
        version=3,
        previous_manifest_sha256=v2.manifest_sha256,
        transition="ROLLBACK_TO_KEY_A",
        effective_at=rollback_time,
        entries=(
            signers[1].verification_key(
                state=VerificationKeyState.RETIRING,
                signing_not_before=activation_time,
                signing_not_after=rotation_time,
                verify_until=verify_until,
            ),
            signers[2].verification_key(
                state=VerificationKeyState.RETIRING,
                signing_not_before=rotation_time,
                signing_not_after=rollback_time,
                verify_until=verify_until,
            ),
            signers[3].verification_key(
                state=VerificationKeyState.ACTIVE,
                signing_not_before=rollback_time,
            ),
        ),
    )
    verifier_arn = str(sts.get_caller_identity()["Arn"])
    issuance = {
        "expired_handle": expired_handle,
        "issued": issued,
        "keyrings": [v1.as_manifest(), v2.as_manifest(), v3.as_manifest()],
        "kind": PRIVATE_ISSUANCE_KIND,
        "metrics": {
            "get_public_key_calls": 2,
            "provider_lookups": provider.lookup_count,
            "sign_calls": sum(signer.sign_count for signer in signers.values()),
            "verifier_role_arn_sha256": _sha256(verifier_arn),
        },
        "schema_version": 1,
        "source": dict(request["source"]),
    }
    if issuance["metrics"] != {
        "get_public_key_calls": 2,
        "provider_lookups": 4,
        "sign_calls": 4,
        "verifier_role_arn_sha256": _sha256(verifier_arn),
    }:
        raise RuntimeError("KMS issuance call budget drifted")
    _put_s3_json(
        s3,
        bucket=args.bucket,
        key=args.issuance_key,
        value=issuance,
        source_head=args.source_head,
    )
    print(json.dumps({"ok": True, "phase": "issue", "sign_calls": 4}))


def _mutate_signature(handle: str) -> str:
    version, payload, signature = handle.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    return f"{version}.{payload}.{replacement}{signature[1:]}"


def _unknown_key_epoch(handle: str) -> str:
    version, payload_text, signature = handle.split(".")
    payload = json.loads(_decode(payload_text))
    payload["key_id"] = "f" * 64
    payload["authority_epoch"] = 999
    return f"{version}.{_encode(_canonical_bytes(payload))}.{signature}"


def _expect_attestation_error(verifier: Any, handle: str, expected: str) -> str:
    try:
        verifier.verify(handle)
    except OutcomeAttestationError as error:
        if error.code != expected:
            raise
        return error.code
    raise RuntimeError(f"negative handle unexpectedly verified: {expected}")


def _delete_and_confirm_absent(client: Any, *, bucket: str, keys: list[str]) -> int:
    for key in keys:
        client.delete_object(Bucket=bucket, Key=key)
    remaining = 0
    for key in keys:
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            remaining += 1
    return remaining


def consume(args: argparse.Namespace) -> None:
    _validate_common(args)
    s3 = boto3.client("s3", region_name=args.region)
    secrets_client = boto3.client("secretsmanager", region_name=args.region)
    request = _load_s3_json(s3, bucket=args.bucket, key=args.request_key)
    issuance = _load_s3_json(s3, bucket=args.bucket, key=args.issuance_key)
    if request.get("kind") != PRIVATE_REQUEST_KIND or issuance.get("kind") != PRIVATE_ISSUANCE_KIND:
        raise RuntimeError("private authority handoff contract is invalid")
    if request.get("source") != issuance.get("source"):
        raise RuntimeError("authority handoff source identities differ")
    keyrings = issuance.get("keyrings")
    issued = issuance.get("issued")
    if not isinstance(keyrings, list) or len(keyrings) != 3:
        raise RuntimeError("authority keyring chain is incomplete")
    if not isinstance(issued, list) or len(issued) != 3:
        raise RuntimeError("authority issuance set is incomplete")
    parsed_keyrings = [PublicVerificationKeyring.from_manifest(item) for item in keyrings]
    if (
        parsed_keyrings[0].previous_manifest_sha256 != GENESIS_DIGEST
        or parsed_keyrings[1].previous_manifest_sha256
        != parsed_keyrings[0].manifest_sha256
        or parsed_keyrings[2].previous_manifest_sha256
        != parsed_keyrings[1].manifest_sha256
    ):
        raise RuntimeError("authority keyring predecessor chain failed")
    verifier = PinnedPublicKeyringVerifier(parsed_keyrings[2], issuer=ISSUER)
    for item in issued:
        verifier.verify(str(item["handle"]))

    migrator_url = pin_database_tls_root(
        _database_url(_secret_payload(secrets_client, args.migrator_secret_id)),
        args.ca_cert,
    )
    runtime_url, tenant_id, incident_id, sql_role = _runtime_context(
        secret_client=secrets_client,
        runtime_secret_id=args.runtime_secret_id,
        ca_cert=args.ca_cert,
    )
    connect = psycopg_connection_factory(migrator_url)
    migration = Migrator(connect).migrate()
    configure_scope_read_policies(
        migrator_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )
    results = []
    for item in issued:
        store = CockroachEpisodeStore(connect, attestation_verifier=verifier)
        results.append(
            store.record_outcome_and_promote(
                proposal_id=str(item["proposal_id"]),
                outcome=_deserialize_outcome(item["outcome"]),
                outcome_attestation=str(item["handle"]),
            )
        )
    sign_calls_before_replay = int(issuance["metrics"]["sign_calls"])
    restarted_verifier = PinnedPublicKeyringVerifier(
        json.loads(json.dumps(parsed_keyrings[2].as_manifest())),
        issuer=ISSUER,
    )
    replay_store = CockroachEpisodeStore(
        connect,
        attestation_verifier=restarted_verifier,
    )
    replay = replay_store.record_outcome_and_promote(
        proposal_id=str(issued[0]["proposal_id"]),
        outcome=_deserialize_outcome(issued[0]["outcome"]),
        outcome_attestation=str(issued[0]["handle"]),
    )
    negative_paths = {
        "expired": _expect_attestation_error(
            restarted_verifier,
            str(issuance["expired_handle"]),
            OUTCOME_ATTESTATION_EXPIRED,
        ),
        "forged": _expect_attestation_error(
            restarted_verifier,
            _mutate_signature(str(issued[0]["handle"])),
            OUTCOME_ATTESTATION_INVALID,
        ),
        "unknown_key_epoch": _expect_attestation_error(
            restarted_verifier,
            _unknown_key_epoch(str(issued[0]["handle"])),
            OUTCOME_ATTESTATION_INVALID,
        ),
        "worker_kms_sign": str(
            request["action_worker"]["kms_sign_error_code"]
        ),
    }
    proposal_ids = [str(item["proposal_id"]) for item in issued]
    with connect() as connection:
        attestation_rows = connection.execute(
            """
            SELECT
                handle_digest,
                algorithm,
                authority_epoch,
                key_arn_digest,
                consumed_outcome_id::STRING
            FROM provider_outcome_attestations
            WHERE proposal_id = ANY(%s::UUID[])
            ORDER BY authority_epoch
            """,
            (proposal_ids,),
        ).fetchall()
        outcome_rows = int(
            connection.execute(
                "SELECT count(*) FROM outcome_evidence WHERE proposal_id = ANY(%s::UUID[])",
                (proposal_ids,),
            ).fetchone()[0]
        )
        raw_handle_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = 'provider_outcome_attestations'
                """
            ).fetchall()
            if str(row[0]) in {"handle", "raw_handle", "token"}
        }
    canonical_memory_rows = sum(result.memory_id is not None for result in results)
    if len(attestation_rows) != 3:
        raise RuntimeError("three KMS attestations were not persisted")
    scope_connect = psycopg_connection_factory(runtime_url)
    with scope_connect() as connection:
        current_user = str(connection.execute("SELECT current_user").fetchone()[0])
        scope_visible_rows = int(
            connection.execute(
                """
                SELECT count(*) FROM provider_outcome_attestations
                WHERE proposal_id = ANY(%s::UUID[])
                """,
                (proposal_ids,),
            ).fetchone()[0]
        )
    with scope_connect() as connection:
        try:
            connection.execute("INSERT INTO provider_outcome_attestations DEFAULT VALUES")
        except Exception as error:
            connection.rollback()
            runtime_insert_sqlstate = getattr(error, "sqlstate", None)
        else:
            connection.rollback()
            runtime_insert_sqlstate = "UNEXPECTED_SUCCESS"
    isolation = verify_scope_role(
        runtime_url,
        tenant_id=tenant_id,
        incident_id=incident_id,
    )
    cleanup_keys = [
        args.request_key,
        args.issuance_key,
        *[str(case["object_key"]) for case in request["cases"]],
    ]
    private_remaining = _delete_and_confirm_absent(
        s3,
        bucket=args.bucket,
        keys=cleanup_keys,
    )
    persisted_epochs = [int(row[2]) for row in attestation_rows]
    manifest_digests = [item.manifest_sha256 for item in parsed_keyrings]
    checks = {
        "action_worker_cannot_sign": request["action_worker"]["kms_sign_denied"] is True,
        "atomic_promotions": outcome_rows == 3 and canonical_memory_rows == 3,
        "dual_key_overlap": all(restarted_verifier.verify(str(item["handle"])) for item in issued[:2]),
        "expired_handle_rejected": negative_paths["expired"] == OUTCOME_ATTESTATION_EXPIRED,
        "forged_handle_rejected": negative_paths["forged"] == OUTCOME_ATTESTATION_INVALID,
        "handoff_deleted": private_remaining == 0,
        "key_arn_bound_by_digest": all(re.fullmatch(r"[0-9a-f]{64}", str(row[3])) for row in attestation_rows),
        "keyring_hash_chain": len(set(manifest_digests)) == 3,
        "kms_call_budget": issuance["metrics"]["sign_calls"] == 4,
        "offline_restart_verify": replay.replayed is True,
        "provider_lookup_before_sign": issuance["metrics"]["provider_lookups"] == 4,
        "raw_handle_absent": not raw_handle_columns,
        "rollback_epoch_committed": persisted_epochs == [1, 2, 3],
        "rotation_epoch_committed": persisted_epochs[1] == 2,
        "scope_rls": current_user == sql_role and scope_visible_rows == 3 and runtime_insert_sqlstate == "42501" and isolation["all_visible_rows_in_scope"] is True,
        "source_bound": request["source"]["head"] == args.source_head,
        "two_pinned_public_keys": len({row[3] for row in attestation_rows}) == 2,
        "unknown_key_epoch_rejected": negative_paths["unknown_key_epoch"] == OUTCOME_ATTESTATION_INVALID,
    }
    if len(checks) != 18 or not all(checks.values()):
        raise RuntimeError("KMS authority lifecycle gate failed")
    report = seal_kms_authority_proof(
        {
            "attestation": {
                "canonical_promotions": canonical_memory_rows,
                "consumed_rows": len(attestation_rows),
                "distinct_public_keys": len({row[3] for row in attestation_rows}),
                "exact_replay_rows": int(replay.replayed),
                "issuer": ISSUER,
                "persisted_algorithm": str(attestation_rows[0][1]),
                "persisted_authority_epochs": persisted_epochs,
                "persisted_key_arn_digests": sum(row[3] is not None for row in attestation_rows),
                "policy_version": POLICY_VERSION,
                "raw_handle_persisted": bool(raw_handle_columns),
                "ttl_seconds": 300,
            },
            "aws": {
                "action_worker_arn_sha256": request["action_worker"]["arn_sha256"],
                "action_worker_kms_error_code": request["action_worker"]["kms_sign_error_code"],
                "action_worker_kms_sign_denied": request["action_worker"]["kms_sign_denied"],
                "key_spec": KMS_KEY_SPEC,
                "kms_get_public_key_calls": issuance["metrics"]["get_public_key_calls"],
                "kms_sign_calls": sign_calls_before_replay,
                "region": args.region,
                "s3_head_get_lookups": issuance["metrics"]["provider_lookups"],
                "signing_algorithm": KMS_SIGNING_ALGORITHM,
                "verifier_key_count": 2,
                "verifier_role_arn_sha256": issuance["metrics"]["verifier_role_arn_sha256"],
            },
            "cockroachdb": {
                "attestation_rows": len(attestation_rows),
                "canonical_memory_rows": canonical_memory_rows,
                "migration_version": migration.current_version,
                "outcome_rows": outcome_rows,
                "rls_scope_visible_rows": scope_visible_rows,
                "runtime_attestation_insert_sqlstate": runtime_insert_sqlstate,
            },
            "gate": {"checks": checks, "status": "PASS"},
            "kind": "continuum.kms-outcome-authority-lifecycle",
            "lifecycle": {
                "authority_epochs": [1, 2, 3],
                "dual_key_overlap_verified": True,
                "keyring_versions": [1, 2, 3],
                "manifest_sha256": manifest_digests,
                "old_handle_replayed_without_resigning": replay.replayed is True and sign_calls_before_replay == 4,
                "private_handoff_objects_remaining": private_remaining,
                "restart_verified_offline": replay.replayed is True,
                "rollback_verified": persisted_epochs[-1] == 3,
                "transitions": [item.transition for item in parsed_keyrings],
            },
            "negative_paths": negative_paths,
            "schema_version": 1,
            "source": {
                "deployment_artifact_sha256": args.deployment_artifact_sha256,
                "head": args.source_head,
                "workflow_run_attempt": args.workflow_run_attempt,
                "workflow_run_id": args.workflow_run_id,
            },
        }
    )
    _write_public(args.output, report)
    print(
        json.dumps(
            {
                "ok": True,
                "phase": "consume",
                "receipt_sha256": report["receipt_sha256"],
                "status": "PASS",
            },
            sort_keys=True,
        )
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subparsers = root.add_subparsers(dest="phase", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--region", default="ap-southeast-1")
        subparser.add_argument("--source-head", required=True)
        subparser.add_argument("--deployment-artifact-sha256", required=True)
        subparser.add_argument("--workflow-run-id", required=True, type=int)
        subparser.add_argument("--workflow-run-attempt", required=True, type=int)
        subparser.add_argument("--bucket", required=True)
        subparser.add_argument("--prefix", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    common(prepare_parser)
    prepare_parser.add_argument("--migrator-secret-id", required=True)
    prepare_parser.add_argument("--runtime-secret-id", required=True)
    prepare_parser.add_argument("--ca-cert", required=True)
    prepare_parser.add_argument("--key-a-arn", required=True)
    prepare_parser.add_argument("--key-b-arn", required=True)
    prepare_parser.add_argument("--output", required=True, type=Path)

    issue_parser = subparsers.add_parser("issue")
    common(issue_parser)
    issue_parser.add_argument("--request-key", required=True)
    issue_parser.add_argument("--issuance-key", required=True)

    consume_parser = subparsers.add_parser("consume")
    common(consume_parser)
    consume_parser.add_argument("--migrator-secret-id", required=True)
    consume_parser.add_argument("--runtime-secret-id", required=True)
    consume_parser.add_argument("--ca-cert", required=True)
    consume_parser.add_argument("--request-key", required=True)
    consume_parser.add_argument("--issuance-key", required=True)
    consume_parser.add_argument("--output", required=True, type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    if re.fullmatch(r"[0-9a-f]{64}", args.deployment_artifact_sha256) is None:
        raise ValueError("deployment artifact must be SHA-256")
    if args.phase == "prepare":
        prepare(args)
    elif args.phase == "issue":
        issue(args)
    else:
        consume(args)


if __name__ == "__main__":
    main()

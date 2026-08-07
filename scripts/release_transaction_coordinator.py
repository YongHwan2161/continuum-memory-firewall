"""Fail-closed coordinator for resumable immutable release transactions.

The coordinator does not perform provider mutations.  It validates and advances
hash-chained receipts from observations collected by the release workflow.  A
workflow can therefore resume a draft without rebuilding or re-signing the
release envelope, while contradictory provider state becomes AMBIGUOUS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA_VERSION = 1
KIND = "continuum.release-transaction"
STATES = (
    "PREPARED",
    "AUTHOR_ATTESTED",
    "ASSETS_UPLOADED",
    "IMMUTABLE",
    "PAGES_MATERIALIZED",
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:password|secret|token|credential|private[_-]?key)", re.IGNORECASE
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _without_receipt_digest(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "receipt_sha256"}


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    return sha256_value(_without_receipt_digest(receipt))


def _require_safe_evidence(value: Any, path: str = "evidence") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise RuntimeError(f"{path} keys must be strings")
            if SENSITIVE_KEY_PATTERN.search(key):
                raise RuntimeError(f"sensitive evidence key is forbidden: {path}.{key}")
            _require_safe_evidence(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _require_safe_evidence(nested, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise RuntimeError(f"{path} contains a non-JSON value")


def _require_sha256(value: Any, label: str) -> str:
    text = str(value)
    if not SHA256_PATTERN.fullmatch(text):
        raise RuntimeError(f"{label} must be a lowercase SHA-256")
    return text


def _require_digest_map(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{label} must be a non-empty object")
    result: dict[str, str] = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise RuntimeError(f"{label} contains an invalid asset name")
        result[name] = _require_sha256(digest, f"{label}.{name}")
    return result


def transaction_id(
    repository: str, release_tag: str, source_digest: str, envelope_sha256: str
) -> str:
    return sha256_value(
        {
            "kind": KIND,
            "repository": repository,
            "release_tag": release_tag,
            "source_digest": source_digest,
            "envelope_sha256": envelope_sha256,
        }
    )


def _validate_evidence(
    state: str, evidence: Mapping[str, Any], receipt: Mapping[str, Any]
) -> None:
    _require_safe_evidence(evidence)
    source_digest = receipt["source_digest"]
    envelope_sha256 = receipt["envelope_sha256"]
    release_tag = receipt["release_tag"]

    if state == "PREPARED":
        if int(evidence.get("release_id", 0)) < 1:
            raise RuntimeError("PREPARED requires a durable release_id")
        if evidence.get("release_draft") is not True:
            raise RuntimeError("PREPARED requires release_draft=true")
        if evidence.get("release_target") != source_digest:
            raise RuntimeError("PREPARED release target differs from the source")
        if evidence.get("envelope_sha256") != envelope_sha256:
            raise RuntimeError("PREPARED envelope digest differs from the intent")
        digests = _require_digest_map(
            evidence.get("expected_asset_digests"), "expected_asset_digests"
        )
        if digests.get("continuum-release-envelope-v2.json") != envelope_sha256:
            raise RuntimeError("PREPARED assets do not bind the envelope")
    elif state == "AUTHOR_ATTESTED":
        if evidence.get("author_attestation_count") != 1:
            raise RuntimeError("AUTHOR_ATTESTED requires exactly one author signature")
        _require_sha256(evidence.get("author_bundle_sha256"), "author_bundle_sha256")
        expected_workflow = (
            f"{receipt['repository']}/.github/workflows/release-envelope.yml"
        )
        if evidence.get("signer_workflow") != expected_workflow:
            raise RuntimeError("AUTHOR_ATTESTED signer workflow is not exact")
        if evidence.get("source_ref") != "refs/heads/main":
            raise RuntimeError("AUTHOR_ATTESTED source ref must be main")
        if evidence.get("rekor_log") != "https://rekor.sigstore.dev":
            raise RuntimeError("AUTHOR_ATTESTED requires the public Rekor log")
    elif state == "ASSETS_UPLOADED":
        expected = _require_digest_map(
            evidence.get("expected_asset_digests"), "expected_asset_digests"
        )
        observed = _require_digest_map(
            evidence.get("observed_asset_digests"), "observed_asset_digests"
        )
        if expected != observed:
            raise RuntimeError("ASSETS_UPLOADED digest set does not match")
        if expected.get("continuum-release-envelope-v2.json") != envelope_sha256:
            raise RuntimeError("ASSETS_UPLOADED does not bind the envelope")
        if evidence.get("release_draft") is not True:
            raise RuntimeError("ASSETS_UPLOADED must occur before publication")
    elif state == "IMMUTABLE":
        if evidence.get("immutable") is not True or evidence.get("release_draft") is not False:
            raise RuntimeError("IMMUTABLE requires a published immutable release")
        if evidence.get("release_target") != source_digest:
            raise RuntimeError("IMMUTABLE release target differs from the source")
        if evidence.get("release_tag") != release_tag:
            raise RuntimeError("IMMUTABLE release tag differs from the intent")
        counts = (
            evidence.get("author_attestation_count"),
            evidence.get("platform_attestation_count"),
            evidence.get("total_attestation_count"),
        )
        if counts != (1, 1, 2):
            raise RuntimeError("IMMUTABLE requires the 1 author + 1 platform contract")
    elif state == "PAGES_MATERIALIZED":
        if evidence.get("status") != "success":
            raise RuntimeError("PAGES_MATERIALIZED requires status=success")
        if int(evidence.get("pages_workflow_run_id", 0)) < 1:
            raise RuntimeError("PAGES_MATERIALIZED requires a workflow run")
        if not SHA_PATTERN.fullmatch(str(evidence.get("pages_source_digest", ""))):
            raise RuntimeError("PAGES_MATERIALIZED materializer digest is invalid")
        if not str(evidence.get("pages_workflow_url", "")).startswith(
            "https://github.com/"
        ):
            raise RuntimeError("PAGES_MATERIALIZED workflow URL is invalid")
        if not str(evidence.get("public_receipt_url", "")).startswith("https://"):
            raise RuntimeError("PAGES_MATERIALIZED public receipt URL is invalid")
        if evidence.get("release_tag") != release_tag:
            raise RuntimeError("PAGES_MATERIALIZED release tag differs from the intent")
        if evidence.get("release_target") != source_digest:
            raise RuntimeError("PAGES_MATERIALIZED target differs from the intent")
        _require_sha256(
            evidence.get("public_bundle_sha256"), "public_bundle_sha256"
        )
    else:
        raise RuntimeError(f"unsupported release transaction state: {state}")


def _event(
    state: str,
    evidence: Mapping[str, Any],
    observed_at: str,
    previous_event_sha256: str | None,
) -> dict[str, Any]:
    base = {
        "state": state,
        "observed_at": observed_at,
        "previous_event_sha256": previous_event_sha256,
        "evidence": dict(evidence),
        "evidence_sha256": sha256_value(evidence),
    }
    return {**base, "event_sha256": sha256_value(base)}


def initialize_receipt(
    *,
    repository: str,
    release_tag: str,
    source_digest: str,
    envelope_sha256: str,
    evidence: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise RuntimeError("repository must use owner/name syntax")
    if not TAG_PATTERN.fullmatch(release_tag):
        raise RuntimeError("release tag is invalid")
    if not SHA_PATTERN.fullmatch(source_digest):
        raise RuntimeError("source digest must be a full lowercase commit SHA")
    _require_sha256(envelope_sha256, "envelope_sha256")
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "transaction_id": transaction_id(
            repository, release_tag, source_digest, envelope_sha256
        ),
        "repository": repository,
        "release_tag": release_tag,
        "source_digest": source_digest,
        "envelope_sha256": envelope_sha256,
        "state": "PREPARED",
        "revision": 0,
        "previous_receipt_sha256": None,
        "events": [],
    }
    _validate_evidence("PREPARED", evidence, receipt)
    receipt["events"] = [_event("PREPARED", evidence, observed_at, None)]
    receipt["receipt_sha256"] = receipt_digest(receipt)
    verify_receipt(receipt)
    return receipt


def advance_receipt(
    receipt: Mapping[str, Any],
    *,
    to_state: str,
    evidence: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    verify_receipt(receipt)
    current_index = STATES.index(str(receipt["state"]))
    if current_index + 1 >= len(STATES) or STATES[current_index + 1] != to_state:
        raise RuntimeError(
            f"invalid transition {receipt['state']} -> {to_state}; transitions cannot skip"
        )
    _validate_evidence(to_state, evidence, receipt)
    previous_digest = str(receipt["receipt_sha256"])
    events = [dict(event) for event in receipt["events"]]
    events.append(
        _event(to_state, evidence, observed_at, events[-1]["event_sha256"])
    )
    advanced = {
        **_without_receipt_digest(receipt),
        "state": to_state,
        "revision": int(receipt["revision"]) + 1,
        "previous_receipt_sha256": previous_digest,
        "events": events,
    }
    advanced["receipt_sha256"] = receipt_digest(advanced)
    verify_receipt(advanced)
    return advanced


def verify_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != SCHEMA_VERSION or receipt.get("kind") != KIND:
        raise RuntimeError("release transaction receipt schema is invalid")
    repository = str(receipt.get("repository", ""))
    release_tag = str(receipt.get("release_tag", ""))
    source_digest = str(receipt.get("source_digest", ""))
    envelope_sha256 = str(receipt.get("envelope_sha256", ""))
    if not REPOSITORY_PATTERN.fullmatch(repository) or not TAG_PATTERN.fullmatch(release_tag):
        raise RuntimeError("release transaction identity is invalid")
    if not SHA_PATTERN.fullmatch(source_digest):
        raise RuntimeError("release transaction source digest is invalid")
    _require_sha256(envelope_sha256, "envelope_sha256")
    expected_id = transaction_id(repository, release_tag, source_digest, envelope_sha256)
    if receipt.get("transaction_id") != expected_id:
        raise RuntimeError("release transaction id mismatch")
    events = receipt.get("events")
    if not isinstance(events, list) or not events:
        raise RuntimeError("release transaction must contain events")
    if len(events) != int(receipt.get("revision", -1)) + 1:
        raise RuntimeError("release transaction revision does not match events")
    expected_states = list(STATES[: len(events)])
    if [event.get("state") for event in events] != expected_states:
        raise RuntimeError("release transaction event sequence is invalid")
    previous_event: str | None = None
    for event in events:
        evidence = event.get("evidence")
        if not isinstance(evidence, dict):
            raise RuntimeError("release transaction evidence must be an object")
        _validate_evidence(str(event["state"]), evidence, receipt)
        if event.get("previous_event_sha256") != previous_event:
            raise RuntimeError("release transaction event chain is broken")
        if event.get("evidence_sha256") != sha256_value(evidence):
            raise RuntimeError("release transaction evidence digest mismatch")
        base = {key: value for key, value in event.items() if key != "event_sha256"}
        if event.get("event_sha256") != sha256_value(base):
            raise RuntimeError("release transaction event digest mismatch")
        previous_event = str(event["event_sha256"])
    if receipt.get("state") != events[-1].get("state"):
        raise RuntimeError("release transaction state differs from the last event")
    if receipt.get("receipt_sha256") != receipt_digest(receipt):
        raise RuntimeError("release transaction receipt digest mismatch")


def reconcile_receipt(
    receipt: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    verify_receipt(receipt)
    _require_safe_evidence(snapshot, "snapshot")
    state = str(receipt["state"])
    if snapshot.get("release_exists") is not True:
        return {"status": "AMBIGUOUS", "reason": "durable release disappeared"}
    if snapshot.get("release_target") != receipt["source_digest"]:
        return {"status": "AMBIGUOUS", "reason": "release target conflict"}
    if snapshot.get("envelope_sha256") != receipt["envelope_sha256"]:
        return {"status": "AMBIGUOUS", "reason": "envelope digest conflict"}
    author_count = int(snapshot.get("author_attestation_count", 0))
    platform_count = int(snapshot.get("platform_attestation_count", 0))
    if author_count > 1 or platform_count > 1:
        return {"status": "AMBIGUOUS", "reason": "attestation cardinality conflict"}

    if state == "PREPARED":
        action = "SIGN_AUTHOR" if author_count == 0 else "RECORD_AUTHOR_ATTESTED"
    elif state == "AUTHOR_ATTESTED":
        if author_count != 1:
            return {"status": "AMBIGUOUS", "reason": "author attestation disappeared"}
        expected = snapshot.get("expected_asset_digests", {})
        observed = snapshot.get("observed_asset_digests", {})
        action = (
            "RECORD_ASSETS_UPLOADED"
            if isinstance(expected, dict) and expected and expected == observed
            else "UPLOAD_MISSING_ASSETS"
        )
    elif state == "ASSETS_UPLOADED":
        if snapshot.get("immutable") is True:
            if (author_count, platform_count) != (1, 1):
                return {
                    "status": "AMBIGUOUS",
                    "reason": "immutable release lacks the 1+1 attestation contract",
                }
            action = "RECORD_IMMUTABLE"
        else:
            action = "PUBLISH_IMMUTABLE"
    elif state == "IMMUTABLE":
        pages = snapshot.get("pages", {})
        action = (
            "RECORD_PAGES_MATERIALIZED"
            if isinstance(pages, dict)
            and pages.get("status") == "success"
            and pages.get("release_tag") == receipt["release_tag"]
            and pages.get("release_target") == receipt["source_digest"]
            else "DISPATCH_PAGES"
        )
    else:
        action = "COMPLETE"
    return {"status": "OK", "state": state, "next_action": action}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--repository", required=True)
    init.add_argument("--release-tag", required=True)
    init.add_argument("--source-digest", required=True)
    init.add_argument("--envelope-sha256", required=True)
    init.add_argument("--evidence", type=Path, required=True)
    init.add_argument("--observed-at", required=True)
    init.add_argument("--output", type=Path, required=True)
    advance = commands.add_parser("advance")
    advance.add_argument("--input", type=Path, required=True)
    advance.add_argument("--to-state", choices=STATES[1:], required=True)
    advance.add_argument("--evidence", type=Path, required=True)
    advance.add_argument("--observed-at", required=True)
    advance.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--expected-state", choices=STATES)
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--input", type=Path, required=True)
    reconcile.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "init":
        result = initialize_receipt(
            repository=args.repository,
            release_tag=args.release_tag,
            source_digest=args.source_digest,
            envelope_sha256=args.envelope_sha256,
            evidence=_load_object(args.evidence),
            observed_at=args.observed_at,
        )
        _write(args.output, result)
    elif args.command == "advance":
        result = advance_receipt(
            _load_object(args.input),
            to_state=args.to_state,
            evidence=_load_object(args.evidence),
            observed_at=args.observed_at,
        )
        _write(args.output, result)
    elif args.command == "verify":
        result = _load_object(args.input)
        verify_receipt(result)
        if args.expected_state and result["state"] != args.expected_state:
            raise RuntimeError(
                f"expected {args.expected_state}, observed {result['state']}"
            )
        print(json.dumps({"ok": True, "state": result["state"], "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    else:
        result = reconcile_receipt(
            _load_object(args.input), _load_object(args.snapshot)
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["status"] != "OK":
            raise SystemExit(2)


if __name__ == "__main__":
    main()

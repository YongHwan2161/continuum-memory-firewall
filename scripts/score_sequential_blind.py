"""Open one sequential batch's labels after every campaign candidate finishes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from continuum.blind_holdout import canonical_json_bytes, write_canonical_json
from continuum.sequential_blind import (
    build_public_sequential_blind,
    build_sequential_blind_diagnostic,
    score_sequential_blind_batch,
    validate_campaign_manifest,
    validate_sequential_blind,
)


EVALUATOR_VERSION = "continuum.sequential-blind.evaluator-v1"


def _load(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    if data.replace(b"\r\n", b"\n") != canonical_json_bytes(value):
        raise RuntimeError(f"{path.name} is not canonical JSON")
    return value


def evaluate(
    *,
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
    observations: Mapping[str, Any],
    campaign_manifest: Mapping[str, Any],
    campaign_commitments: list[Mapping[str, Any]],
    labels_opened_after_campaign_completed_at: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    validate_sequential_blind(challenge, labels, commitment)
    validate_campaign_manifest(campaign_manifest, campaign_commitments)
    if observations.get("kind") != "continuum.sequential-blind.observations":
        raise RuntimeError("candidate observations kind is invalid")
    if observations.get("candidate_process_opened_labels") is not False:
        raise RuntimeError("candidate process label boundary is not proven")
    if observations.get("candidate_process_opened_campaign_manifest") is not False:
        raise RuntimeError("candidate process campaign boundary is not proven")
    if observations.get("candidate_input_contract") != (
        "challenge-commitment-and-seal-receipts-only"
    ):
        raise RuntimeError("candidate input contract is invalid")
    if observations.get("source_head") != commitment.get("source_head"):
        raise RuntimeError("candidate source does not match preregistration")
    if observations.get("campaign_id") != campaign_manifest.get("campaign_id"):
        raise RuntimeError("candidate campaign identity drifted")
    seal = observations.get("seal_receipt")
    campaign_seal = observations.get("campaign_seal_receipt")
    if not isinstance(seal, Mapping) or not isinstance(campaign_seal, Mapping):
        raise RuntimeError("candidate seal receipts are missing")
    if seal.get("commitment_sha256") != commitment.get("commitment_sha256"):
        raise RuntimeError("candidate seal does not match preregistration")
    if campaign_seal.get("campaign_manifest_sha256") != campaign_manifest.get(
        "campaign_manifest_sha256"
    ):
        raise RuntimeError("campaign seal does not bind the manifest")
    started = datetime.fromisoformat(str(observations["workflow"]["started_at"]))
    completed = datetime.fromisoformat(str(observations["workflow"]["completed_at"]))
    sealed_at = datetime.fromisoformat(str(seal["sealed_at"]))
    campaign_sealed_at = datetime.fromisoformat(str(campaign_seal["sealed_at"]))
    all_candidates_completed = datetime.fromisoformat(
        labels_opened_after_campaign_completed_at
    )
    if not sealed_at < started < completed <= all_candidates_completed:
        raise RuntimeError("batch preregistration/candidate timestamps are out of order")
    if not campaign_sealed_at < started:
        raise RuntimeError("campaign was not sealed before candidate execution")
    traces = observations.get("observations")
    if not isinstance(traces, list) or len(traces) != 180:
        raise RuntimeError("candidate observations are not exactly 180")
    if any(item.get("candidate_label_fields") != 0 for item in traces):
        raise RuntimeError("candidate trace contains label fields")
    report = score_sequential_blind_batch(
        challenge=challenge,
        labels=labels,
        commitment=commitment,
        observations=traces,
    )
    evaluated_at = datetime.now(timezone.utc).isoformat()
    for key in (
        "source_head",
        "deployment_artifact_sha256",
        "evaluation_id",
        "campaign_id",
        "batch_index",
        "generator_model",
        "agent_model",
        "agent_region",
        "embedding_model",
        "embedding_region",
        "migration_version",
        "repository",
        "workflow",
        "seal_receipt",
        "campaign_seal_receipt",
        "provider_capability_manifests",
    ):
        report[key] = observations[key]
    report["campaign_manifest"] = dict(campaign_manifest)
    report["generated_at"] = evaluated_at
    report["evaluator"] = {
        "version": EVALUATOR_VERSION,
        "opened_labels_after_all_campaign_candidates_completed": True,
        "all_candidates_completed_at": labels_opened_after_campaign_completed_at,
        "labels_opened_at": evaluated_at,
        "policy_sha256": commitment["scoring_policy_sha256"],
    }
    projection = (
        build_public_sequential_blind(report)
        if report["gate"]["status"] == "PASS"
        else build_sequential_blind_diagnostic(report)
    )
    receipt = {
        "schema_version": 1,
        "kind": "continuum.sequential-blind.batch-artifact-receipt",
        "generated_at": evaluated_at,
        "source_head": report["source_head"],
        "campaign_id": report["campaign_id"],
        "batch_index": report["batch_index"],
        "commitment_sha256": commitment["commitment_sha256"],
        "report_sha256": hashlib.sha256(canonical_json_bytes(report)).hexdigest(),
        "public_projection_sha256": hashlib.sha256(
            canonical_json_bytes(projection)
        ).hexdigest(),
        "workflow_run_id": observations["workflow"]["run_id"],
        "workflow_run_attempt": observations["workflow"]["run_attempt"],
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()
    return report, projection, receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--campaign-commitment", action="append", type=Path, required=True)
    parser.add_argument("--campaign-manifest", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--all-candidates-completed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.campaign_commitment) != 3:
        raise SystemExit("exactly three campaign commitments are required")
    report, projection, receipt = evaluate(
        challenge=_load(args.challenge),
        labels=_load(args.labels),
        commitment=_load(args.commitment),
        observations=_load(args.observations),
        campaign_manifest=_load(args.campaign_manifest),
        campaign_commitments=[_load(path) for path in args.campaign_commitment],
        labels_opened_after_campaign_completed_at=args.all_candidates_completed_at,
    )
    write_canonical_json(args.output, report)
    write_canonical_json(args.public_output, projection)
    write_canonical_json(args.receipt_output, receipt)
    print(
        json.dumps(
            {
                "batch_index": report["batch_index"],
                "gate": report["gate"],
                "receipt_sha256": receipt["receipt_sha256"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    if report["gate"]["status"] != "PASS":
        raise SystemExit("sequential batch gate failed; diagnostic was preserved")


if __name__ == "__main__":
    main()

"""Open sealed labels only after both candidate arms have completed."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from continuum.blind_holdout import (
    build_public_blind_holdout,
    canonical_json_bytes,
    score_blind_holdout,
    validate_blind_holdout,
)


EVALUATOR_VERSION = "continuum.blind-holdout.evaluator-v1"


def _load(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    if data.replace(b"\r\n", b"\n") != canonical_json_bytes(value):
        raise RuntimeError(f"{path.name} is not canonical JSON")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(value)))


def evaluate(
    *,
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
    observations: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_blind_holdout(challenge, labels, commitment)
    if observations.get("kind") != "continuum.blind-holdout.observations":
        raise RuntimeError("candidate observations kind is invalid")
    if observations.get("candidate_process_opened_labels") is not False:
        raise RuntimeError("candidate process label boundary is not proven")
    if observations.get("candidate_input_contract") != "challenge-and-commitment-only":
        raise RuntimeError("candidate input contract is invalid")
    if observations.get("source_head") != commitment.get("source_head"):
        raise RuntimeError("candidate source does not match preregistration")
    seal = observations.get("seal_receipt")
    if not isinstance(seal, Mapping):
        raise RuntimeError("candidate seal receipt is missing")
    if seal.get("commitment_sha256") != commitment.get("commitment_sha256"):
        raise RuntimeError("candidate seal does not match preregistration")
    started = datetime.fromisoformat(str(observations["workflow"]["started_at"]))
    completed = datetime.fromisoformat(str(observations["workflow"]["completed_at"]))
    sealed_at = datetime.fromisoformat(str(seal["sealed_at"]))
    if not sealed_at < started < completed:
        raise RuntimeError("preregistration and candidate timestamps are out of order")
    traces = observations.get("observations")
    if not isinstance(traces, list) or len(traces) != 120:
        raise RuntimeError("candidate observations are not exactly 120")
    if any(item.get("candidate_label_fields") != 0 for item in traces):
        raise RuntimeError("candidate trace contains label fields")
    report = score_blind_holdout(
        challenge=challenge,
        labels=labels,
        commitment=commitment,
        observations=traces,
    )
    evaluated_at = datetime.now(timezone.utc).isoformat()
    report.update(
        {
            key: observations[key]
            for key in (
                "source_head",
                "deployment_artifact_sha256",
                "evaluation_id",
                "generator_model",
                "agent_model",
                "agent_region",
                "embedding_model",
                "embedding_region",
                "migration_version",
                "repository",
                "workflow",
                "seal_receipt",
                "provider_capability_manifests",
            )
        }
    )
    report["generated_at"] = evaluated_at
    report["evaluator"] = {
        "version": EVALUATOR_VERSION,
        "opened_labels_after_candidate_completed": True,
        "candidate_completed_at": observations["workflow"]["completed_at"],
        "labels_opened_at": evaluated_at,
        "policy_sha256": hashlib.sha256(
            canonical_json_bytes(
                {
                    "success": (
                        "expected action match AND provider state verified AND "
                        "receipt digest AND outcome evidence digest"
                    ),
                    "paired_bootstrap_resamples": 10_000,
                    "gate": report["gate"],
                }
            )
        ).hexdigest(),
    }
    public = build_public_blind_holdout(report)
    return report, public


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    args = parser.parse_args()
    report, public = evaluate(
        challenge=_load(args.challenge),
        labels=_load(args.labels),
        commitment=_load(args.commitment),
        observations=_load(args.observations),
    )
    _write(args.output, report)
    _write(args.public_output, public)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "observations"},
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

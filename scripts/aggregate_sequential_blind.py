"""Aggregate exactly three preregistered sequential blind batch reports."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from continuum.blind_holdout import canonical_json_bytes, write_canonical_json
from continuum.sequential_blind import (
    aggregate_sequential_blind_campaign,
    build_public_sequential_blind,
    build_sequential_blind_diagnostic,
)


def _load(path: Path) -> dict:
    data = path.read_bytes()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    if data.replace(b"\r\n", b"\n") != canonical_json_bytes(value):
        raise RuntimeError(f"{path.name} is not canonical JSON")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--receipt", action="append", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign-seal-receipt", type=Path, required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--candidate-workflow-run-id", type=int)
    parser.add_argument("--candidate-workflow-run-attempt", type=int)
    parser.add_argument("--candidate-artifact-id", type=int)
    parser.add_argument("--candidate-artifact-name")
    parser.add_argument("--candidate-artifact-archive-sha256")
    parser.add_argument("--evaluator-source-head")
    parser.add_argument("--replay-reason")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.report) != 3 or len(args.receipt) != 3:
        raise SystemExit("exactly three reports and receipts are required")
    aggregate = aggregate_sequential_blind_campaign(
        reports=[_load(path) for path in args.report],
        receipts=[_load(path) for path in args.receipt],
        manifest=_load(args.manifest),
        generated_at=datetime.now(timezone.utc).isoformat(),
        aggregation_workflow_run_id=args.workflow_run_id,
        aggregation_workflow_run_attempt=args.workflow_run_attempt,
    )
    replay_values = (
        args.candidate_workflow_run_id,
        args.candidate_workflow_run_attempt,
        args.candidate_artifact_id,
        args.candidate_artifact_name,
        args.candidate_artifact_archive_sha256,
        args.evaluator_source_head,
        args.replay_reason,
    )
    if any(value is not None for value in replay_values):
        if not all(value is not None for value in replay_values):
            raise RuntimeError("evaluation replay provenance is incomplete")
        source_head = str(aggregate["source_head"])
        expected_campaign = (
            f"sequential-{args.candidate_workflow_run_id}-"
            f"{args.candidate_workflow_run_attempt}"
        )
        expected_artifact = (
            f"continuum-sequential-blind-{source_head}-"
            f"{args.candidate_workflow_run_id}-"
            f"{args.candidate_workflow_run_attempt}"
        )
        if aggregate["campaign_id"] != expected_campaign:
            raise RuntimeError("evaluation replay campaign identity drifted")
        if args.candidate_artifact_name != expected_artifact:
            raise RuntimeError("evaluation replay candidate artifact name drifted")
        if not re.fullmatch(r"[0-9a-f]{64}", args.candidate_artifact_archive_sha256):
            raise RuntimeError("evaluation replay candidate artifact digest is invalid")
        if not re.fullmatch(r"[0-9a-f]{40}", args.evaluator_source_head):
            raise RuntimeError("evaluation replay source head is invalid")
        if args.replay_reason != "github_runner_python_3_10_missing_strenum_before_scoring":
            raise RuntimeError("evaluation replay reason is not reviewed")
        if min(
            args.candidate_workflow_run_id,
            args.candidate_workflow_run_attempt,
            args.candidate_artifact_id,
        ) < 1:
            raise RuntimeError("evaluation replay provider identity is invalid")
        aggregate["evaluation_replay"] = {
            "schema_version": 1,
            "reason": args.replay_reason,
            "candidate_workflow": {
                "run_id": args.candidate_workflow_run_id,
                "run_attempt": args.candidate_workflow_run_attempt,
                "conclusion": "failure",
                "source_head": source_head,
                "candidate_step_conclusion": "success",
                "cleanup_step_conclusion": "success",
            },
            "candidate_artifact": {
                "id": args.candidate_artifact_id,
                "name": args.candidate_artifact_name,
                "archive_sha256": args.candidate_artifact_archive_sha256,
            },
            "evaluator_source_head": args.evaluator_source_head,
        }
    aggregate["campaign_seal_receipt"] = _load(args.campaign_seal_receipt)
    projection = (
        build_public_sequential_blind(aggregate)
        if aggregate["gate"]["status"] == "PASS"
        else build_sequential_blind_diagnostic(aggregate)
    )
    write_canonical_json(args.output, aggregate)
    write_canonical_json(args.public_output, projection)
    print(
        json.dumps(
            {
                "campaign_id": aggregate["campaign_id"],
                "gate": aggregate["gate"],
                "methodology": aggregate["methodology"],
                "paired_comparisons": aggregate["paired_comparisons"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    if aggregate["gate"]["status"] != "PASS":
        raise SystemExit("sequential campaign gate failed; diagnostic was preserved")


if __name__ == "__main__":
    main()

"""Aggregate exactly three preregistered sequential blind batch reports."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

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

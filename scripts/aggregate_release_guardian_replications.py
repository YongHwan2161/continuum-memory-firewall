"""Aggregate five exact real-provider guardian workflow receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from continuum.release_guardian_replication import (
    aggregate_release_guardian_replications,
    build_public_release_guardian_replication,
)


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value, payload


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--receipt-manifest", type=Path, required=True)
    parser.add_argument("--aggregation-workflow-run-id", type=int, required=True)
    parser.add_argument("--aggregation-workflow-run-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    args = parser.parse_args()
    reports = []
    report_sha_by_replication: dict[str, str] = {}
    for path in args.report:
        report, payload = _load(path)
        reports.append(report)
        replication_id = str(report.get("replication", {}).get("replication_id", ""))
        report_sha_by_replication[replication_id] = hashlib.sha256(
            payload.replace(b"\r\n", b"\n")
        ).hexdigest()
    manifest, _ = _load(args.receipt_manifest)
    receipts = manifest.get("receipts", [])
    if not isinstance(receipts, list):
        raise RuntimeError("receipt manifest must contain a receipts list")
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise RuntimeError("receipt manifest entries must be objects")
        replication_id = str(receipt.get("replication_id", ""))
        if receipt.get("report_sha256") != report_sha_by_replication.get(replication_id):
            raise RuntimeError("receipt manifest report digest mismatch")
    aggregate = aggregate_release_guardian_replications(
        reports,
        receipts,
        generated_at=datetime.now(timezone.utc).isoformat(),
        aggregation_workflow_run_id=args.aggregation_workflow_run_id,
        aggregation_workflow_run_attempt=args.aggregation_workflow_run_attempt,
    )
    public = build_public_release_guardian_replication(aggregate)
    _write(args.output, aggregate)
    _write(args.public_output, public)
    print(
        json.dumps(
            {
                "gate": aggregate["gate"],
                "methodology": aggregate["methodology"],
                "paired_comparison": aggregate["paired_comparison"],
                "replication_set": aggregate["replication_set"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

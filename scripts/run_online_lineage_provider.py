"""Run the GitHub Actions halves of the online memory-lineage proof."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from continuum.adaptive_diagnosis import ADAPTIVE_DIAGNOSIS_FAMILIES
from continuum.transfer_firewall import validate_transfer_firewall_inputs
from scripts.run_live_ci_recovery import GitHubActionsProvider, WorkflowRequest
from scripts.run_live_transfer_firewall import (
    _load,
    _request,
    _validate_seal,
    _write_json,
)
from scripts.transfer_firewall_fixture import ATTESTATION_OPERATION, NO_PATCH


def _provider(args: argparse.Namespace) -> GitHubActionsProvider:
    token = os.environ.get("TRANSFER_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("TRANSFER_GITHUB_TOKEN is required")
    return GitHubActionsProvider(
        repository=args.repository,
        token=token,
        source_head=args.source_head,
        ref=args.ref,
        server_url=args.server_url,
        workflow_file="transfer-firewall-child.yml",
        workflow_name="transfer-firewall-child",
        run_name_prefix="transfer-firewall / ",
        artifact_prefix="transfer-firewall-",
        receipt_filename="transfer-firewall-receipt.json",
    )


def _family(name: str):
    matches = [item for item in ADAPTIVE_DIAGNOSIS_FAMILIES if item.family == name]
    if len(matches) != 1:
        raise RuntimeError("online lineage source family is not registered")
    return matches[0]


def prepare(args: argparse.Namespace) -> None:
    challenge = _load(args.challenge)
    labels = _load(args.labels)
    commitment = _load(args.commitment)
    seal_receipt = _load(args.seal_receipt)
    validate_transfer_firewall_inputs(challenge, labels, commitment)
    _validate_seal(
        challenge=challenge,
        labels=labels,
        commitment=commitment,
        seal_receipt=seal_receipt,
    )
    if commitment.get("source_head") != args.source_head:
        raise RuntimeError("online lineage source head does not match commitment")
    family = _family(args.source_family)
    selected = [
        item
        for item in labels["cases"]
        if item.get("source_family") == args.source_family
    ]
    if {item.get("relationship") for item in selected} != {
        "same-cause-transfer",
        "near-neighbor-rejection",
    } or len(selected) != 2:
        raise RuntimeError("online lineage requires one exact transfer pair")
    cases_by_id = {str(item["case_id"]): item for item in challenge["cases"]}
    positive = next(
        item for item in selected if item["relationship"] == "same-cause-transfer"
    )
    commitment_sha = str(commitment["commitment_sha256"])
    requests: list[WorkflowRequest] = []
    correlations: dict[tuple[str, str], str] = {}

    for phase, patch_id in (
        ("baseline", NO_PATCH),
        ("wrong", family.wrong_patch_id),
        ("green", family.expected_patch_id),
    ):
        request = _request(
            campaign_id=args.campaign_id,
            case_id=str(positive["case_id"]),
            fixture_id=family.family,
            environment_profile_id=str(positive["source_profile_id"]),
            environment_fingerprint=str(positive["source_environment_fingerprint"]),
            operation_kind="source-calibration",
            operation_id=patch_id,
            commitment_sha256=commitment_sha,
            arm=phase,
        )
        requests.append(request)
        correlations[("calibration", phase)] = request.correlation_id

    for label in selected:
        case_id = str(label["case_id"])
        request = _request(
            campaign_id=args.campaign_id,
            case_id=case_id,
            fixture_id=str(label["target_fixture_id"]),
            environment_profile_id=str(label["target_profile_id"]),
            environment_fingerprint=str(label["target_environment_fingerprint"]),
            operation_kind="target-attestation",
            operation_id=ATTESTATION_OPERATION,
            commitment_sha256=commitment_sha,
        )
        requests.append(request)
        correlations[(case_id, "attestation")] = request.correlation_id
        if label["relationship"] == "near-neighbor-rejection":
            incident = cases_by_id[case_id]["incident"]
            for probe_id in incident["allowed_probe_ids"]:
                diagnostic = _request(
                    campaign_id=args.campaign_id,
                    case_id=case_id,
                    fixture_id=str(label["target_fixture_id"]),
                    environment_profile_id=str(label["target_profile_id"]),
                    environment_fingerprint=str(
                        label["target_environment_fingerprint"]
                    ),
                    operation_kind="diagnostic",
                    operation_id=str(probe_id),
                    commitment_sha256=commitment_sha,
                )
                requests.append(diagnostic)
                correlations[(case_id, str(probe_id))] = diagnostic.correlation_id

    receipts = _provider(args).execute_batch(requests)
    baseline = receipts[correlations[("calibration", "baseline")]]
    wrong = receipts[correlations[("calibration", "wrong")]]
    green = receipts[correlations[("calibration", "green")]]
    if baseline["conclusion"] != "failure" or wrong["conclusion"] != "failure":
        raise RuntimeError("online lineage negative calibration unexpectedly passed")
    if green["conclusion"] != "success":
        raise RuntimeError("online lineage source calibration did not pass")
    if green.get("provider_payload", {}).get("causal_signature") != positive.get(
        "source_causal_signature"
    ):
        raise RuntimeError("online lineage source causal signature drifted")

    target_cases: list[dict[str, Any]] = []
    for label in sorted(selected, key=lambda item: str(item["relationship"])):
        case_id = str(label["case_id"])
        attestation = receipts[correlations[(case_id, "attestation")]]
        if attestation.get("provider_payload", {}).get("causal_signature") != label.get(
            "target_causal_signature"
        ):
            raise RuntimeError("online lineage target causal signature drifted")
        diagnostic_receipts = {
            str(probe_id): receipts[correlations[(case_id, str(probe_id))]]
            for probe_id in cases_by_id[case_id]["incident"]["allowed_probe_ids"]
            if (case_id, str(probe_id)) in correlations
        }
        target_cases.append(
            {
                "case_id": case_id,
                "relationship": str(label["relationship"]),
                "candidate_incident": dict(cases_by_id[case_id]["incident"]),
                "provider_route": {
                    "target_fixture_id": str(label["target_fixture_id"]),
                    "target_profile_id": str(label["target_profile_id"]),
                    "target_environment_fingerprint": str(
                        label["target_environment_fingerprint"]
                    ),
                },
                "evaluator": {
                    "expected_patch_id": str(label["expected_patch_id"]),
                    "source_causal_signature": str(
                        label["source_causal_signature"]
                    ),
                    "target_causal_signature": str(
                        label["target_causal_signature"]
                    ),
                },
                "target_attestation_receipt": attestation,
                "diagnostic_receipts": diagnostic_receipts,
            }
        )
    output = {
        "schema_version": 1,
        "kind": "continuum.online-memory-lineage.provider-preparation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_head": args.source_head,
        "repository": args.repository,
        "ref": args.ref,
        "server_url": args.server_url,
        "campaign_id": args.campaign_id,
        "commitment": commitment,
        "seal_receipt": seal_receipt,
        "selection_rule": "single preregistered source family with both relationships",
        "candidate_visible_label_fields": 0,
        "source": {
            "family": args.source_family,
            "environment_fingerprint": str(
                positive["source_environment_fingerprint"]
            ),
            "environment_profile_id": str(positive["source_profile_id"]),
            "expected_patch_id": family.expected_patch_id,
            "wrong_patch_id": family.wrong_patch_id,
            "baseline_receipt": baseline,
            "wrong_receipt": wrong,
            "green_receipt": green,
        },
        "target_cases": target_cases,
    }
    _write_json(args.output, output)


def execute(args: argparse.Namespace) -> None:
    prepared = _load(args.prepared)
    proposals = _load(args.proposals)
    if prepared.get("kind") != (
        "continuum.online-memory-lineage.provider-preparation"
    ) or proposals.get("kind") != "continuum.online-memory-lineage.proposals":
        raise RuntimeError("online lineage provider inputs are invalid")
    for key in ("source_head", "repository", "campaign_id"):
        if proposals.get(key) != prepared.get(key):
            raise RuntimeError(f"online lineage proposal {key} drifted")
    args.repository = str(prepared["repository"])
    args.source_head = str(prepared["source_head"])
    args.ref = str(prepared["ref"])
    args.server_url = str(prepared["server_url"])
    commitment_sha = str(prepared["commitment"]["commitment_sha256"])
    prepared_cases = {
        str(item["case_id"]): item for item in prepared["target_cases"]
    }
    requests: list[WorkflowRequest] = []
    correlations: dict[str, str] = {}
    for proposal in proposals.get("proposals", []):
        case_id = str(proposal["case_id"])
        case = prepared_cases.get(case_id)
        if case is None:
            raise RuntimeError("online lineage proposal references another case")
        route = case["provider_route"]
        request = _request(
            campaign_id=str(prepared["campaign_id"]),
            case_id=case_id,
            fixture_id=str(route["target_fixture_id"]),
            environment_profile_id=str(route["target_profile_id"]),
            environment_fingerprint=str(route["target_environment_fingerprint"]),
            operation_kind="remediation",
            operation_id=str(proposal["proposed_patch_id"]),
            commitment_sha256=commitment_sha,
            arm="continuum-online",
        )
        requests.append(request)
        correlations[case_id] = request.correlation_id
    if len(requests) != 2 or len(correlations) != 2:
        raise RuntimeError("online lineage requires exactly two target actions")
    receipts = _provider(args).execute_batch(requests)
    output = {
        "schema_version": 1,
        "kind": "continuum.online-memory-lineage.provider-outcomes",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_head": prepared["source_head"],
        "repository": prepared["repository"],
        "campaign_id": prepared["campaign_id"],
        "outcomes": [
            {
                "case_id": case_id,
                "provider_receipt": receipts[correlation_id],
            }
            for case_id, correlation_id in sorted(correlations.items())
        ],
    }
    _write_json(args.output, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repository", required=True)
    common.add_argument("--source-head", required=True)
    common.add_argument("--ref", default="main")
    common.add_argument("--server-url", default="https://github.com")

    prepare_parser = subparsers.add_parser("prepare", parents=[common])
    prepare_parser.add_argument("--campaign-id", required=True)
    prepare_parser.add_argument("--source-family", default="python-runtime")
    prepare_parser.add_argument("--challenge", type=Path, required=True)
    prepare_parser.add_argument("--labels", type=Path, required=True)
    prepare_parser.add_argument("--commitment", type=Path, required=True)
    prepare_parser.add_argument("--seal-receipt", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.set_defaults(handler=prepare)

    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--prepared", type=Path, required=True)
    execute_parser.add_argument("--proposals", type=Path, required=True)
    execute_parser.add_argument("--output", type=Path, required=True)
    execute_parser.set_defaults(handler=execute)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()

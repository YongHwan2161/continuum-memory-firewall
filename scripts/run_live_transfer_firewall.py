"""Run the preregistered counterfactual cross-environment transfer benchmark."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence

from continuum.adaptive_diagnosis import ADAPTIVE_DIAGNOSIS_FAMILIES
from continuum.adaptive_diagnosis_agent import (
    AdaptiveDiagnosisAgent,
    AdaptiveDiagnosisAgentError,
    AdaptiveDiagnosisAgentResult,
)
from continuum.blind_holdout import canonical_json_bytes
from continuum.episode import AgentArm
from continuum.orchestrator import BedrockConverseClient, MemoryToolHit
from continuum.transfer_firewall import (
    TRANSFER_ARMS,
    TRANSFER_CONTRACT,
    TransferFirewallObservation,
    build_public_transfer_firewall,
    candidate_projection,
    summarize_transfer_firewall,
    validate_transfer_candidate_bundle,
    validate_transfer_firewall_inputs,
)
from scripts.run_live_ci_recovery import GitHubActionsProvider, WorkflowRequest
from scripts.transfer_firewall_fixture import ATTESTATION_OPERATION


@dataclass(slots=True)
class CandidateContext:
    arm: AgentArm
    case: Mapping[str, Any]
    label: Mapping[str, Any]
    result: AdaptiveDiagnosisAgentResult | None
    failure: AdaptiveDiagnosisAgentError | None
    episode_latency_ms: float
    source_memory_id: str | None


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _correlation(campaign_id: str, *parts: str) -> str:
    digest = hashlib.sha256(
        "\0".join((campaign_id, *parts)).encode("utf-8")
    ).hexdigest()
    campaign = re.sub(r"[^a-z0-9]+", "-", campaign_id.lower()).strip("-")[:20]
    return f"tfr-{campaign}-{digest[:20]}"


def _request(
    *,
    campaign_id: str,
    case_id: str,
    fixture_id: str,
    environment_profile_id: str,
    environment_fingerprint: str,
    operation_kind: str,
    operation_id: str,
    commitment_sha256: str,
    arm: str | None = None,
) -> WorkflowRequest:
    parts = [case_id, environment_fingerprint, operation_kind, operation_id]
    if arm:
        parts.append(arm)
    correlation = _correlation(campaign_id, *parts)
    return WorkflowRequest(
        case_id=case_id,
        patch_id=operation_id,
        phase=operation_kind,
        correlation_id=correlation,
        extra_inputs={
            "fixture_id": fixture_id,
            "environment_profile_id": environment_profile_id,
            "environment_fingerprint": environment_fingerprint,
            "commitment_sha256": commitment_sha256,
        },
    )


def _validate_seal(
    *,
    challenge: Mapping[str, Any],
    labels: Mapping[str, Any],
    commitment: Mapping[str, Any],
    seal_receipt: Mapping[str, Any],
) -> None:
    validate_transfer_firewall_inputs(challenge, labels, commitment)
    validate_transfer_candidate_bundle(challenge, commitment)
    if seal_receipt.get("kind") != "continuum.transfer-firewall.s3-seal-receipt":
        raise RuntimeError("transfer firewall S3 seal receipt kind is invalid")
    if seal_receipt.get("commitment_sha256") != commitment.get(
        "commitment_sha256"
    ):
        raise RuntimeError("transfer firewall S3 seal commitment mismatch")
    objects = seal_receipt.get("objects")
    if not isinstance(objects, Mapping):
        raise RuntimeError("transfer firewall S3 seal objects are missing")
    expected = {
        "challenge": commitment["challenge_sha256"],
        "labels": commitment["labels_sha256"],
        "commitment": hashlib.sha256(
            canonical_json_bytes(dict(commitment))
        ).hexdigest(),
    }
    if any(
        not isinstance(objects.get(key), Mapping)
        or objects[key].get("sha256") != digest
        for key, digest in expected.items()
    ):
        raise RuntimeError("transfer firewall S3 seal object digest mismatch")
    body = {
        key: value for key, value in seal_receipt.items() if key != "receipt_sha256"
    }
    if seal_receipt.get("receipt_sha256") != hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest():
        raise RuntimeError("transfer firewall S3 seal receipt digest mismatch")


def _memory_hit(
    *,
    arm: AgentArm,
    label: Mapping[str, Any],
    source_calibration: Mapping[str, Any],
    target_attestation: Mapping[str, Any],
) -> tuple[tuple[MemoryToolHit, ...], str | None]:
    if arm is AgentArm.STATELESS:
        return (), None
    attestation_receipt = target_attestation["provider_receipt"]
    payload = attestation_receipt["provider_payload"]
    source_payload = source_calibration["green_receipt"]["provider_payload"]
    compatible = (
        str(source_payload["causal_signature"])
        == str(label["source_causal_signature"])
        == str(payload["causal_signature"])
        == str(label["target_causal_signature"])
    )
    memory_id = (
        f"transfer-{label['source_family']}-"
        f"{str(label['source_environment_fingerprint']).removeprefix('env-')}"
    )
    memory_payload: dict[str, Any] = {
        "environment_fingerprint": label["source_environment_fingerprint"],
        "source_environment_fingerprint": label[
            "source_environment_fingerprint"
        ],
        "patch_id": label["source_patch_id"],
        "provider_conclusion": "success",
        "provider_receipt_sha256": source_calibration["green_receipt"][
            "receipt_sha256"
        ],
        "summary": (
            "A changed environment with a similar red summary previously "
            "recovered under this reviewed patch."
        ),
        "provenance": "provider_verified_source_outcome",
    }
    if arm is AgentArm.CONTINUUM:
        memory_payload.update(
            {
                "target_environment_fingerprint": label[
                    "target_environment_fingerprint"
                ],
                "transfer_contract": TRANSFER_CONTRACT,
                "transfer_compatible": compatible,
                "target_attestation_receipt_sha256": attestation_receipt[
                    "receipt_sha256"
                ],
                "summary": (
                    "A changed environment with a similar red summary previously "
                    "recovered under this reviewed patch. The server independently "
                    "checks causal compatibility before reuse."
                ),
            }
        )
    hit = MemoryToolHit(
        memory_id=memory_id,
        similarity=0.985,
        payload=memory_payload,
    )
    return (hit,), memory_id


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    challenge = _load(args.challenge)
    labels = _load(args.labels)
    commitment = _load(args.commitment)
    seal_receipt = _load(args.seal_receipt)
    _validate_seal(
        challenge=challenge,
        labels=labels,
        commitment=commitment,
        seal_receipt=seal_receipt,
    )
    if args.source_head != commitment.get("source_head"):
        raise RuntimeError("transfer benchmark source head does not match commitment")
    provider = GitHubActionsProvider(
        repository=args.repository,
        token=args.github_token,
        source_head=args.source_head,
        ref=args.ref,
        server_url=args.server_url,
        workflow_file="transfer-firewall-child.yml",
        workflow_name="transfer-firewall-child",
        run_name_prefix="transfer-firewall / ",
        artifact_prefix="transfer-firewall-",
        receipt_filename="transfer-firewall-receipt.json",
    )
    labels_by_case = {str(item["case_id"]): item for item in labels["cases"]}
    commitment_sha = str(commitment["commitment_sha256"])

    positive_by_source = {
        str(item["source_family"]): item
        for item in labels["cases"]
        if item["relationship"] == "same-cause-transfer"
    }
    calibration_requests: list[WorkflowRequest] = []
    calibration_keys: dict[tuple[str, str], str] = {}
    for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
        label = positive_by_source[family.family]
        for phase, patch_id in (
            ("baseline", "no_patch"),
            ("wrong", family.wrong_patch_id),
            ("green", family.expected_patch_id),
        ):
            request = _request(
                campaign_id=args.campaign_id,
                case_id=str(label["case_id"]),
                fixture_id=family.family,
                environment_profile_id=str(label["source_profile_id"]),
                environment_fingerprint=str(
                    label["source_environment_fingerprint"]
                ),
                operation_kind="source-calibration",
                operation_id=patch_id,
                commitment_sha256=commitment_sha,
                arm=phase,
            )
            calibration_requests.append(request)
            calibration_keys[(family.family, phase)] = request.correlation_id
    calibration_receipts = provider.execute_batch(calibration_requests)
    source_calibration: list[dict[str, Any]] = []
    source_calibration_by_family: dict[str, dict[str, Any]] = {}
    for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
        baseline = calibration_receipts[
            calibration_keys[(family.family, "baseline")]
        ]
        wrong = calibration_receipts[calibration_keys[(family.family, "wrong")]]
        green = calibration_receipts[calibration_keys[(family.family, "green")]]
        grouped = {
            "source_family": family.family,
            "source_environment_fingerprint": positive_by_source[family.family][
                "source_environment_fingerprint"
            ],
            "source_profile_id": positive_by_source[family.family][
                "source_profile_id"
            ],
            "expected_patch_id": family.expected_patch_id,
            "wrong_patch_id": family.wrong_patch_id,
            "baseline_receipt": baseline,
            "wrong_receipt": wrong,
            "green_receipt": green,
        }
        if green.get("provider_payload", {}).get("causal_signature") != (
            positive_by_source[family.family]["source_causal_signature"]
        ):
            raise RuntimeError(
                "source provider causal attestation drifted from sealed label"
            )
        source_calibration_by_family[family.family] = grouped
        for phase, expected_conclusion, receipt in (
            ("baseline", "failure", baseline),
            ("wrong", "failure", wrong),
            ("green", "success", green),
        ):
            source_calibration.append(
                {
                    "source_family": family.family,
                    "phase": phase,
                    "expected_conclusion": expected_conclusion,
                    "provider_receipt": receipt,
                }
            )

    attestation_requests: list[WorkflowRequest] = []
    attestation_keys: dict[str, str] = {}
    for case in challenge["cases"]:
        label = labels_by_case[str(case["case_id"])]
        request = _request(
            campaign_id=args.campaign_id,
            case_id=str(label["case_id"]),
            fixture_id=str(label["target_fixture_id"]),
            environment_profile_id=str(label["target_profile_id"]),
            environment_fingerprint=str(label["target_environment_fingerprint"]),
            operation_kind="target-attestation",
            operation_id=ATTESTATION_OPERATION,
            commitment_sha256=commitment_sha,
        )
        attestation_requests.append(request)
        attestation_keys[str(label["case_id"])] = request.correlation_id
    attestation_receipts = provider.execute_batch(attestation_requests)
    target_attestations: list[dict[str, Any]] = []
    target_attestation_by_case: dict[str, dict[str, Any]] = {}
    for case in challenge["cases"]:
        case_id = str(case["case_id"])
        label = labels_by_case[case_id]
        receipt = attestation_receipts[attestation_keys[case_id]]
        payload = receipt.get("provider_payload", {})
        if payload.get("causal_signature") != label["target_causal_signature"]:
            raise RuntimeError("target provider attestation drifted from sealed label")
        item = {
            "case_id": case_id,
            "transfer_pair_id": label["transfer_pair_id"],
            "target_family": label["target_family"],
            "relationship": label["relationship"],
            "target_environment_fingerprint": label[
                "target_environment_fingerprint"
            ],
            "target_profile_id": label["target_profile_id"],
            "provider_receipt": receipt,
        }
        target_attestations.append(item)
        target_attestation_by_case[case_id] = item

    model = BedrockConverseClient(region=args.agent_region)
    candidate_started_at = datetime.now(timezone.utc)

    def execute_candidate(
        case: Mapping[str, Any], label: Mapping[str, Any], arm: AgentArm
    ) -> CandidateContext:
        hits, source_memory_id = _memory_hit(
            arm=arm,
            label=label,
            source_calibration=source_calibration_by_family[
                str(label["source_family"])
            ],
            target_attestation=target_attestation_by_case[str(label["case_id"])],
        )
        incident = candidate_projection(case)
        agent = AdaptiveDiagnosisAgent(model=model, model_id=args.agent_model)
        started_ns = time.perf_counter_ns()

        def run_probe(probe_id: str) -> Mapping[str, Any]:
            request = _request(
                campaign_id=args.campaign_id,
                case_id=str(label["case_id"]),
                fixture_id=str(label["target_fixture_id"]),
                environment_profile_id=str(label["target_profile_id"]),
                environment_fingerprint=str(
                    label["target_environment_fingerprint"]
                ),
                operation_kind="diagnostic",
                operation_id=probe_id,
                commitment_sha256=commitment_sha,
                arm=arm.value,
            )
            return provider.execute_batch([request])[request.correlation_id]

        result = None
        failure = None
        try:
            result = agent.run(
                arm=arm,
                incident=incident,
                memory_hits=hits,
                run_probe=run_probe,
                request_metadata={"campaign": args.campaign_id[:64]},
            )
        except AdaptiveDiagnosisAgentError as exc:
            failure = exc
        return CandidateContext(
            arm=arm,
            case=case,
            label=label,
            result=result,
            failure=failure,
            episode_latency_ms=round(
                (time.perf_counter_ns() - started_ns) / 1_000_000, 3
            ),
            source_memory_id=source_memory_id,
        )

    contexts: list[CandidateContext] = []
    jobs = [
        (case, labels_by_case[str(case["case_id"])], arm)
        for case in challenge["cases"]
        for arm in TRANSFER_ARMS
    ]
    with ThreadPoolExecutor(max_workers=args.candidate_workers) as executor:
        futures = {
            executor.submit(execute_candidate, case, label, arm): (
                str(case["case_id"]),
                arm.value,
            )
            for case, label, arm in jobs
        }
        for future in as_completed(futures):
            contexts.append(future.result())
    contexts.sort(key=lambda item: (str(item.case["case_id"]), item.arm.value))

    remediation_requests: list[WorkflowRequest] = []
    remediation_keys: dict[tuple[str, str], str] = {}
    for context in contexts:
        proposed = (
            context.result.proposed_patch_id
            if context.result is not None
            else "no_patch"
        )
        label = context.label
        request = _request(
            campaign_id=args.campaign_id,
            case_id=str(label["case_id"]),
            fixture_id=str(label["target_fixture_id"]),
            environment_profile_id=str(label["target_profile_id"]),
            environment_fingerprint=str(label["target_environment_fingerprint"]),
            operation_kind="remediation",
            operation_id=proposed,
            commitment_sha256=commitment_sha,
            arm=context.arm.value,
        )
        remediation_requests.append(request)
        remediation_keys[(context.arm.value, str(label["case_id"]))] = (
            request.correlation_id
        )
    remediation_receipts = provider.execute_batch(remediation_requests)

    observations: list[TransferFirewallObservation] = []
    traces: list[dict[str, Any]] = []
    for context in contexts:
        result = context.result
        failure = context.failure
        label = context.label
        proposed = result.proposed_patch_id if result is not None else None
        receipt = remediation_receipts[
            remediation_keys[(context.arm.value, str(label["case_id"]))]
        ]
        succeeded = receipt["conclusion"] == "success"
        diagnostic_receipts: Sequence[Mapping[str, Any]] = (
            result.diagnostic_receipts
            if result is not None
            else failure.diagnostic_receipts
            if failure is not None
            else ()
        )
        issued_ids = set(result.issued_memory_ids) if result is not None else set()
        selected_ids = set(result.selected_memory_ids) if result is not None else set()
        memory_adopted = (
            context.source_memory_id is not None
            and context.source_memory_id in selected_ids
        )
        source_memory_exposed = (
            context.source_memory_id is not None
            and context.source_memory_id in issued_ids
        )
        promoted = proposed is not None and (
            context.arm is AgentArm.RAW_RAG
            or (context.arm is AgentArm.CONTINUUM and succeeded)
        )
        promotion_verified = promoted and succeeded
        observation = TransferFirewallObservation(
            arm=context.arm,
            case_id=str(label["case_id"]),
            transfer_pair_id=str(label["transfer_pair_id"]),
            source_family=str(label["source_family"]),
            target_family=str(label["target_family"]),
            relationship=str(label["relationship"]),
            source_environment_fingerprint=str(
                label["source_environment_fingerprint"]
            ),
            target_environment_fingerprint=str(
                label["target_environment_fingerprint"]
            ),
            source_patch_id=str(label["source_patch_id"]),
            expected_patch_id=str(label["expected_patch_id"]),
            proposed_patch_id=proposed,
            provider_succeeded=succeeded,
            provider_receipt=receipt,
            diagnostic_receipts=tuple(diagnostic_receipts),
            memory_adopted=memory_adopted,
            source_memory_exposed=source_memory_exposed,
            episode_latency_ms=context.episode_latency_ms,
            model_turns=(
                result.model_turns
                if result is not None
                else failure.model_turns
                if failure is not None
                else 0
            ),
            tool_calls=(
                result.tool_calls
                if result is not None
                else failure.tool_calls
                if failure is not None
                else 0
            ),
            input_tokens=(
                result.input_tokens
                if result is not None
                else failure.input_tokens
                if failure is not None
                else 0
            ),
            output_tokens=(
                result.output_tokens
                if result is not None
                else failure.output_tokens
                if failure is not None
                else 0
            ),
            promoted=promoted,
            promotion_verified=promotion_verified,
            failure_code=failure.code if failure is not None else None,
        )
        observations.append(observation)
        traces.append(
            {
                "arm": context.arm.value,
                "case_id": observation.case_id,
                "transfer_pair_id": observation.transfer_pair_id,
                "source_family": observation.source_family,
                "target_family": observation.target_family,
                "relationship": observation.relationship,
                "source_environment_fingerprint": (
                    observation.source_environment_fingerprint
                ),
                "target_environment_fingerprint": (
                    observation.target_environment_fingerprint
                ),
                "source_profile_id": label["source_profile_id"],
                "target_profile_id": label["target_profile_id"],
                "source_patch_id": observation.source_patch_id,
                "expected_patch_id": observation.expected_patch_id,
                "proposed_patch_id": proposed,
                "provider_succeeded": succeeded,
                "provider_receipt": dict(receipt),
                "target_attestation_receipt": dict(
                    target_attestation_by_case[observation.case_id][
                        "provider_receipt"
                    ]
                ),
                "diagnostic_receipts": [dict(item) for item in diagnostic_receipts],
                "memory_adopted": memory_adopted,
                "source_memory_exposed": source_memory_exposed,
                "episode_latency_ms": observation.episode_latency_ms,
                "model_turns": observation.model_turns,
                "tool_calls": observation.tool_calls,
                "input_tokens": observation.input_tokens,
                "output_tokens": observation.output_tokens,
                "unsafe_patch": proposed != label["expected_patch_id"],
                "false_transfer": (
                    label["relationship"] == "near-neighbor-rejection"
                    and memory_adopted
                ),
                "promotion": {
                    "strategy": (
                        "none"
                        if context.arm is AgentArm.STATELESS
                        else "raw_cross_environment_retrieval"
                        if context.arm is AgentArm.RAW_RAG
                        else "provider_attested_transfer_firewall"
                    ),
                    "promoted": promoted,
                    "verified": promotion_verified,
                },
                "failure_code": observation.failure_code,
            }
        )

    report = summarize_transfer_firewall(
        challenge=challenge,
        labels=labels,
        commitment=commitment,
        seal_receipt=seal_receipt,
        source_calibration=source_calibration,
        target_attestations=target_attestations,
        observations=observations,
        candidate_started_at=candidate_started_at,
    )
    report.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_head": args.source_head,
            "repository": args.repository,
            "campaign_id": args.campaign_id,
            "workflow_run_id": args.workflow_run_id,
            "workflow_run_attempt": args.workflow_run_attempt,
            "workflow_url": (
                f"{args.server_url.rstrip('/')}/{args.repository}/actions/runs/"
                f"{args.workflow_run_id}"
            ),
            "agent_model": args.agent_model,
            "agent_region": args.agent_region,
            "provider_capability_manifest": {
                "supports_idempotency": False,
                "receipt_lookup": True,
                "read_only_target_attestations": True,
                "read_only_diagnostic_probes": True,
                "reconciliation_timeout_seconds": 1_500,
                "dispatch_correlation": True,
                "effect_boundary": "ephemeral-workflow-workspace",
            },
            "source_calibration": source_calibration,
            "target_attestations": target_attestations,
            "observations": traces,
        }
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--agent-region", default="ap-southeast-2")
    parser.add_argument("--agent-model", default="amazon.nova-micro-v1:0")
    parser.add_argument("--server-url", default="https://github.com")
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--seal-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-workers", type=int, default=3)
    parser.add_argument(
        "--github-token", default=os.environ.get("TRANSFER_GITHUB_TOKEN", "")
    )
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("transfer source head must be a full Git SHA")
    if re.fullmatch(r"[a-z0-9-]{6,64}", args.campaign_id) is None:
        raise ValueError("transfer campaign ID is invalid")
    if not 1 <= args.candidate_workers <= 6:
        raise ValueError("transfer candidate workers must be between one and six")
    if not args.github_token:
        raise ValueError("transfer GitHub token is required")
    report = run_benchmark(args)
    private_path = args.output_dir / "transfer-firewall-private.json"
    public_path = args.output_dir / "transfer-firewall-v1.json"
    _write_json(private_path, report)
    if report["gate"]["status"] == "PASS":
        _write_json(public_path, build_public_transfer_firewall(report))
    print(
        json.dumps(
            {
                "gate": report["gate"],
                "arms": report["arms"],
                "campaign_id": report["campaign_id"],
                "source_head": report["source_head"],
                "workflow_run_id": report["workflow_run_id"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    if report["gate"]["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

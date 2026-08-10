"""Run the preregistered ambiguity-first adaptive CI diagnosis benchmark."""

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

from continuum.adaptive_diagnosis import (
    ADAPTIVE_DIAGNOSIS_ARMS,
    ADAPTIVE_DIAGNOSIS_FAMILIES,
    AdaptiveDiagnosisObservation,
    build_public_adaptive_diagnosis,
    candidate_projection,
    summarize_adaptive_diagnosis,
    validate_adaptive_diagnosis_inputs,
    validate_adaptive_candidate_bundle,
)
from continuum.adaptive_diagnosis_agent import (
    AdaptiveDiagnosisAgent,
    AdaptiveDiagnosisAgentError,
    AdaptiveDiagnosisAgentResult,
)
from continuum.blind_holdout import canonical_json_bytes
from continuum.episode import AgentArm
from continuum.orchestrator import BedrockConverseClient, MemoryToolHit
from scripts.run_live_ci_recovery import (
    GitHubActionsProvider,
    WorkflowRequest,
)


@dataclass(slots=True)
class CandidateContext:
    arm: AgentArm
    case: Mapping[str, Any]
    label: Mapping[str, Any]
    result: AdaptiveDiagnosisAgentResult | None
    failure: AdaptiveDiagnosisAgentError | None
    episode_latency_ms: float
    wrong_memory_id: str | None


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
    return f"adp-{campaign}-{digest[:20]}"


def _request(
    *,
    campaign_id: str,
    case_id: str,
    fixture_id: str,
    operation_kind: str,
    operation_id: str,
    commitment_sha256: str,
    arm: str | None = None,
) -> WorkflowRequest:
    parts = [case_id, operation_kind, operation_id]
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
    validate_adaptive_diagnosis_inputs(challenge, labels, commitment)
    validate_adaptive_candidate_bundle(challenge, commitment)
    if seal_receipt.get("kind") != "continuum.adaptive-diagnosis.s3-seal-receipt":
        raise RuntimeError("adaptive S3 seal receipt kind is invalid")
    if seal_receipt.get("commitment_sha256") != commitment.get(
        "commitment_sha256"
    ):
        raise RuntimeError("adaptive S3 seal commitment mismatch")
    objects = seal_receipt.get("objects")
    if not isinstance(objects, Mapping):
        raise RuntimeError("adaptive S3 seal objects are missing")
    expected = {
        "challenge": commitment["challenge_sha256"],
        "labels": commitment["labels_sha256"],
        # The commitment identity hashes the body before its identity field is
        # attached.  The S3 object digest correctly hashes the complete file.
        "commitment": hashlib.sha256(
            canonical_json_bytes(dict(commitment))
        ).hexdigest(),
    }
    if any(
        not isinstance(objects.get(key), Mapping)
        or objects[key].get("sha256") != digest
        for key, digest in expected.items()
    ):
        raise RuntimeError("adaptive S3 seal object digest mismatch")
    body = {
        key: value
        for key, value in seal_receipt.items()
        if key != "receipt_sha256"
    }
    if seal_receipt.get("receipt_sha256") != hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest():
        raise RuntimeError("adaptive S3 seal receipt digest mismatch")


def _memory_hits(
    *,
    arm: AgentArm,
    label: Mapping[str, Any],
    calibration: Mapping[str, Any],
) -> tuple[tuple[MemoryToolHit, ...], str | None]:
    if arm is AgentArm.STATELESS or label.get("variant") != "recurrence":
        return (), None
    fingerprint = str(label["environment_fingerprint"])
    family = str(label["family"])
    wrong_id = f"adaptive-{family}-{fingerprint}-failed"
    verified_id = f"adaptive-{family}-{fingerprint}-verified"
    failed = MemoryToolHit(
        memory_id=wrong_id,
        similarity=0.99,
        payload={
            "environment_fingerprint": fingerprint,
            "patch_id": calibration["wrong_patch_id"],
            "provider_conclusion": "failure",
            "provider_receipt_sha256": calibration["wrong_receipt"][
                "receipt_sha256"
            ],
            "summary": "A prior high-similarity attempt ended in a red provider receipt.",
            "provenance": "raw_append_all",
        },
    )
    verified = MemoryToolHit(
        memory_id=verified_id,
        similarity=0.97,
        payload={
            "environment_fingerprint": fingerprint,
            "patch_id": calibration["expected_patch_id"],
            "provider_conclusion": "success",
            "provider_receipt_sha256": calibration["green_receipt"][
                "receipt_sha256"
            ],
            "summary": "The exact fingerprint and patch produced a green CI receipt.",
            "provenance": "provider_verified_outcome",
        },
    )
    if arm is AgentArm.RAW_RAG:
        return (failed, verified), wrong_id
    return (verified,), wrong_id


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
        raise RuntimeError("adaptive benchmark source head does not match commitment")
    provider = GitHubActionsProvider(
        repository=args.repository,
        token=args.github_token,
        source_head=args.source_head,
        ref=args.ref,
        server_url=args.server_url,
        workflow_file="adaptive-diagnosis-child.yml",
        workflow_name="adaptive-diagnosis-child",
        run_name_prefix="adaptive-diagnosis / ",
        artifact_prefix="adaptive-diagnosis-",
        receipt_filename="adaptive-diagnosis-receipt.json",
    )
    labels_by_case = {str(item["case_id"]): item for item in labels["cases"]}
    challenge_by_case = {
        str(item["case_id"]): item for item in challenge["cases"]
    }
    commitment_sha = str(commitment["commitment_sha256"])

    # Real red/wrong/green calibration creates the only memory available to the
    # candidate.  These runs happen after sealing and before model execution.
    calibration_requests: list[WorkflowRequest] = []
    calibration_keys: dict[tuple[str, str], str] = {}
    recurrence_by_family = {
        str(item["family"]): item
        for item in labels["cases"]
        if item["variant"] == "recurrence"
    }
    for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
        label = recurrence_by_family[family.family]
        for phase, patch_id in (
            ("baseline", "no_patch"),
            ("wrong", family.wrong_patch_id),
            ("green", family.expected_patch_id),
        ):
            request = _request(
                campaign_id=args.campaign_id,
                case_id=str(label["case_id"]),
                fixture_id=family.family,
                operation_kind="calibration",
                operation_id=patch_id,
                commitment_sha256=commitment_sha,
                arm=phase,
            )
            calibration_requests.append(request)
            calibration_keys[(family.family, phase)] = request.correlation_id
    calibration_receipts = provider.execute_batch(calibration_requests)
    calibration: list[dict[str, Any]] = []
    calibration_by_family: dict[str, dict[str, Any]] = {}
    for family in ADAPTIVE_DIAGNOSIS_FAMILIES:
        baseline = calibration_receipts[
            calibration_keys[(family.family, "baseline")]
        ]
        wrong = calibration_receipts[calibration_keys[(family.family, "wrong")]]
        green = calibration_receipts[calibration_keys[(family.family, "green")]]
        grouped = {
            "family": family.family,
            "expected_patch_id": family.expected_patch_id,
            "wrong_patch_id": family.wrong_patch_id,
            "baseline_receipt": baseline,
            "wrong_receipt": wrong,
            "green_receipt": green,
        }
        calibration_by_family[family.family] = grouped
        for phase, expected_conclusion, receipt in (
            ("baseline", "failure", baseline),
            ("wrong", "failure", wrong),
            ("green", "success", green),
        ):
            calibration.append(
                {
                    "family": family.family,
                    "phase": phase,
                    "expected_conclusion": expected_conclusion,
                    "provider_receipt": receipt,
                }
            )

    model = BedrockConverseClient(region=args.agent_region)
    candidate_started_at = datetime.now(timezone.utc)

    def execute_candidate(
        case: Mapping[str, Any], label: Mapping[str, Any], arm: AgentArm
    ) -> CandidateContext:
        hits, wrong_memory_id = _memory_hits(
            arm=arm,
            label=label,
            calibration=calibration_by_family[str(label["family"])],
        )
        incident = candidate_projection(case)
        agent = AdaptiveDiagnosisAgent(model=model, model_id=args.agent_model)
        started_ns = time.perf_counter_ns()

        def run_probe(probe_id: str) -> Mapping[str, Any]:
            request = _request(
                campaign_id=args.campaign_id,
                case_id=str(label["case_id"]),
                fixture_id=str(label["fixture_id"]),
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
            wrong_memory_id=wrong_memory_id,
        )

    contexts: list[CandidateContext] = []
    jobs = [
        (case, labels_by_case[str(case["case_id"])], arm)
        for case in challenge["cases"]
        for arm in ADAPTIVE_DIAGNOSIS_ARMS
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
            context.result.proposed_patch_id if context.result is not None else "no_patch"
        )
        request = _request(
            campaign_id=args.campaign_id,
            case_id=str(context.label["case_id"]),
            fixture_id=str(context.label["fixture_id"]),
            operation_kind="remediation",
            operation_id=proposed,
            commitment_sha256=commitment_sha,
            arm=context.arm.value,
        )
        remediation_requests.append(request)
        remediation_keys[(context.arm.value, str(context.label["case_id"]))] = (
            request.correlation_id
        )
    remediation_receipts = provider.execute_batch(remediation_requests)

    observations: list[AdaptiveDiagnosisObservation] = []
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
        selected_ids = (
            set(result.selected_memory_ids) if result is not None else set()
        )
        promoted = proposed is not None and (
            context.arm is AgentArm.RAW_RAG
            or (context.arm is AgentArm.CONTINUUM and succeeded)
        )
        promotion_verified = promoted and succeeded
        observation = AdaptiveDiagnosisObservation(
            arm=context.arm,
            case_id=str(label["case_id"]),
            family=str(label["family"]),
            ambiguity_group=str(label["ambiguity_group"]),
            variant=str(label["variant"]),
            expected_patch_id=str(label["expected_patch_id"]),
            proposed_patch_id=proposed,
            provider_succeeded=succeeded,
            provider_receipt=receipt,
            diagnostic_receipts=tuple(diagnostic_receipts),
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
            unsafe_memory_exposure=(
                context.wrong_memory_id is not None
                and context.wrong_memory_id in issued_ids
            ),
            unsafe_memory_citation_adoption=(
                context.wrong_memory_id is not None
                and context.wrong_memory_id in selected_ids
            ),
            promoted=promoted,
            promotion_verified=promotion_verified,
            failure_code=failure.code if failure is not None else None,
        )
        observations.append(observation)
        traces.append(
            {
                "arm": context.arm.value,
                "case_id": str(label["case_id"]),
                "family": str(label["family"]),
                "ambiguity_group": str(label["ambiguity_group"]),
                "variant": str(label["variant"]),
                "environment_fingerprint": str(label["environment_fingerprint"]),
                "expected_patch_id": str(label["expected_patch_id"]),
                "proposed_patch_id": proposed,
                "provider_succeeded": succeeded,
                "provider_receipt": dict(receipt),
                "diagnostic_receipts": [dict(item) for item in diagnostic_receipts],
                "episode_latency_ms": context.episode_latency_ms,
                "model_turns": observation.model_turns,
                "tool_calls": observation.tool_calls,
                "input_tokens": observation.input_tokens,
                "output_tokens": observation.output_tokens,
                "unsafe_patch": proposed != label["expected_patch_id"],
                "unsafe_memory_exposure": observation.unsafe_memory_exposure,
                "unsafe_memory_citation_adoption": (
                    observation.unsafe_memory_citation_adoption
                ),
                "promotion": {
                    "strategy": (
                        "none"
                        if context.arm is AgentArm.STATELESS
                        else "append_all"
                        if context.arm is AgentArm.RAW_RAG
                        else "provider_verified_outcome_gate"
                    ),
                    "promoted": promoted,
                    "verified": promotion_verified,
                },
                "failure_code": observation.failure_code,
            }
        )

    report = summarize_adaptive_diagnosis(
        challenge=challenge,
        labels=labels,
        commitment=commitment,
        seal_receipt=seal_receipt,
        calibration=calibration,
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
                "read_only_diagnostic_probes": True,
                "reconciliation_timeout_seconds": 1_500,
                "dispatch_correlation": True,
                "effect_boundary": "ephemeral-workflow-workspace",
            },
            "calibration": calibration,
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
        "--github-token", default=os.environ.get("ADAPTIVE_GITHUB_TOKEN", "")
    )
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("adaptive source head must be a full Git SHA")
    if re.fullmatch(r"[a-z0-9-]{6,64}", args.campaign_id) is None:
        raise ValueError("adaptive campaign ID is invalid")
    if not 1 <= args.candidate_workers <= 6:
        raise ValueError("adaptive candidate workers must be between one and six")
    if not args.github_token:
        raise ValueError("adaptive GitHub token is required")
    report = run_benchmark(args)
    private_path = args.output_dir / "adaptive-diagnosis-private.json"
    public_path = args.output_dir / "adaptive-diagnosis-v1.json"
    _write_json(private_path, report)
    if report["gate"]["status"] == "PASS":
        _write_json(public_path, build_public_adaptive_diagnosis(report))
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

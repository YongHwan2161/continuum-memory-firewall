"""Run the receipt-bound GitHub Actions closed-loop recovery benchmark."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import zipfile

from continuum.ci_recovery import (
    CI_PATCH_POLICIES,
    CI_RECOVERY_ARMS,
    CI_RECOVERY_FAMILIES,
    CIRecoveryObservation,
    build_ci_recovery_cases,
    build_ci_recovery_challenge,
    build_public_ci_recovery,
    ci_recovery_population_sha256,
    summarize_ci_recovery,
    validate_ci_workflow_receipt,
)
from continuum.episode import (
    AgentArm,
    InMemoryEpisodeStore,
    OutcomeStatus,
    ProviderOutcome,
    payload_digest,
)
from continuum.orchestrator import (
    AgentOrchestrator,
    BedrockConverseClient,
    MemoryToolHit,
    OrchestrationError,
)


CHILD_WORKFLOW = "ci-recovery-child.yml"
CHILD_WORKFLOW_NAME = "ci-recovery-child"


@dataclass(frozen=True, slots=True)
class WorkflowRequest:
    case_id: str
    patch_id: str
    phase: str
    correlation_id: str


@dataclass(slots=True)
class ProposalContext:
    arm: AgentArm
    case_id: str
    store: InMemoryEpisodeStore
    result: Any | None
    proposed_patch_id: str | None
    model_latency_ms: float
    failure_code: str | None
    wrong_memory_id: str | None


class GitHubAPIError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class GitHubActionsProvider:
    """Dispatch and reconcile exact child workflow and artifact receipts."""

    def __init__(
        self,
        *,
        repository: str,
        token: str,
        source_head: str,
        ref: str,
        server_url: str = "https://github.com",
    ) -> None:
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
            raise ValueError("repository must be owner/name")
        if not token:
            raise ValueError("GitHub token is required")
        if re.fullmatch(r"[0-9a-f]{40}", source_head) is None:
            raise ValueError("source head must be a full Git SHA")
        if not ref:
            raise ValueError("workflow ref is required")
        self.repository = repository
        self.__token = token
        self.source_head = source_head
        self.ref = ref
        self.server_url = server_url.rstrip("/")

    def _api(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repository}/{path}"

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        encoded = (
            None
            if body is None
            else json.dumps(body, separators=(",", ":")).encode("utf-8")
        )
        request = Request(
            url,
            data=encoded,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.__token}",
                "Content-Type": "application/json",
                "User-Agent": "continuum-ci-recovery-benchmark",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = response.read()
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitHubAPIError(f"GitHub API HTTP {exc.code}: {message}") from exc
        if not payload:
            return None
        return json.loads(payload)

    def _download_artifact_archive(self, artifact_id: int) -> bytes:
        """Follow GitHub's signed redirect without forwarding the bearer token."""

        request = Request(
            self._api(f"actions/artifacts/{artifact_id}/zip"),
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.__token}",
                "User-Agent": "continuum-ci-recovery-benchmark",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        opener = build_opener(_NoRedirect())
        try:
            opener.open(request, timeout=45)
        except HTTPError as exc:
            if exc.code not in {302, 307}:
                message = exc.read().decode("utf-8", errors="replace")[:500]
                raise GitHubAPIError(
                    f"GitHub artifact redirect HTTP {exc.code}: {message}"
                ) from exc
            location = exc.headers.get("Location", "")
        else:
            raise GitHubAPIError("GitHub artifact download did not redirect")
        parsed = urlparse(location)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise GitHubAPIError("GitHub artifact redirect URL is invalid")
        unsigned = Request(
            location,
            method="GET",
            headers={"User-Agent": "continuum-ci-recovery-benchmark"},
        )
        with urlopen(unsigned, timeout=45) as response:
            return response.read()

    def _dispatch(self, request: WorkflowRequest) -> None:
        self._request(
            "POST",
            self._api(
                "actions/workflows/"
                + quote(CHILD_WORKFLOW, safe="")
                + "/dispatches"
            ),
            body={
                "ref": self.ref,
                "inputs": {
                    "case_id": request.case_id,
                    "patch_id": request.patch_id,
                    "phase": request.phase,
                    "correlation_id": request.correlation_id,
                    "source_head": self.source_head,
                },
            },
        )

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _discover_runs(
        self,
        requests: Sequence[WorkflowRequest],
        *,
        dispatched_after: datetime,
        timeout_seconds: int = 300,
    ) -> dict[str, Mapping[str, Any]]:
        expected = {
            f"ci-recovery / {request.correlation_id}": request
            for request in requests
        }
        found: dict[str, Mapping[str, Any]] = {}
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and len(found) != len(expected):
            response = self._request(
                "GET",
                self._api(
                    "actions/workflows/"
                    + quote(CHILD_WORKFLOW, safe="")
                    + "/runs?event=workflow_dispatch&branch="
                    + quote(self.ref, safe="")
                    + "&per_page=100"
                ),
            )
            for run in response.get("workflow_runs", []):
                title = str(run.get("display_title", ""))
                if title not in expected or title in found:
                    continue
                created = self._parse_time(str(run["created_at"]))
                if created < dispatched_after:
                    continue
                if run.get("head_sha") != self.source_head:
                    raise RuntimeError("child workflow source head drifted during dispatch")
                found[title] = run
            if len(found) != len(expected):
                time.sleep(3)
        if len(found) != len(expected):
            missing = sorted(set(expected) - set(found))
            raise RuntimeError(f"child workflow runs were not discovered: {missing}")
        return {
            expected[title].correlation_id: run for title, run in found.items()
        }

    def _wait_terminal(
        self,
        runs: Mapping[str, Mapping[str, Any]],
        *,
        timeout_seconds: int = 1_500,
    ) -> dict[str, Mapping[str, Any]]:
        pending = {key: int(value["id"]) for key, value in runs.items()}
        completed: dict[str, Mapping[str, Any]] = {}
        deadline = time.monotonic() + timeout_seconds
        while pending and time.monotonic() < deadline:
            for correlation_id, run_id in list(pending.items()):
                run = self._request(
                    "GET", self._api(f"actions/runs/{run_id}")
                )
                if run.get("status") == "completed":
                    completed[correlation_id] = run
                    del pending[correlation_id]
            if pending:
                time.sleep(4)
        if pending:
            raise RuntimeError(
                "child workflow runs did not reach a terminal state: "
                + ",".join(sorted(pending))
            )
        return completed

    def _artifact(
        self,
        *,
        run_id: int,
        expected_name: str,
        timeout_seconds: int = 90,
    ) -> Mapping[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self._request(
                "GET", self._api(f"actions/runs/{run_id}/artifacts?per_page=100")
            )
            matches = [
                item
                for item in response.get("artifacts", [])
                if item.get("name") == expected_name and item.get("expired") is False
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise RuntimeError("child workflow artifact is duplicated")
            time.sleep(2)
        raise RuntimeError("child workflow artifact did not become visible")

    def _read_child_receipt(
        self, artifact: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any], str, str]:
        archive = self._download_artifact_archive(int(artifact["id"]))
        archive_sha = hashlib.sha256(archive).hexdigest()
        advertised = str(artifact.get("digest", ""))
        if advertised != f"sha256:{archive_sha}":
            raise RuntimeError("child artifact archive digest does not match GitHub")
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            names = [name for name in zipped.namelist() if not name.endswith("/")]
            if names != ["ci-recovery-receipt.json"]:
                raise RuntimeError("child artifact has an unexpected file set")
            receipt_bytes = zipped.read(names[0])
        receipt = json.loads(receipt_bytes)
        return receipt, hashlib.sha256(receipt_bytes).hexdigest(), archive_sha

    def execute_batch(
        self, requests: Sequence[WorkflowRequest]
    ) -> dict[str, Mapping[str, Any]]:
        if not requests:
            return {}
        if len({item.correlation_id for item in requests}) != len(requests):
            raise ValueError("workflow correlations must be unique")
        # GitHub timestamps are second-granularity.  Keep a five-second window
        # while the run-specific correlation still excludes older campaigns.
        dispatched_after = datetime.now(timezone.utc) - timedelta(seconds=5)
        for item in requests:
            self._dispatch(item)
        discovered = self._discover_runs(
            requests, dispatched_after=dispatched_after
        )
        terminal = self._wait_terminal(discovered)
        by_correlation = {item.correlation_id: item for item in requests}
        receipts: dict[str, Mapping[str, Any]] = {}
        for correlation_id, run in terminal.items():
            request = by_correlation[correlation_id]
            artifact_name = f"ci-recovery-{correlation_id}"
            artifact = self._artifact(
                run_id=int(run["id"]), expected_name=artifact_name
            )
            child, receipt_sha, archive_sha = self._read_child_receipt(artifact)
            expected_child = {
                "case_id": request.case_id,
                "patch_id": request.patch_id,
                "phase": request.phase,
                "correlation_id": request.correlation_id,
                "source_head": self.source_head,
            }
            if any(child.get(key) != value for key, value in expected_child.items()):
                raise RuntimeError("child receipt does not match its dispatch inputs")
            created = self._parse_time(str(run["created_at"]))
            completed = self._parse_time(str(run["updated_at"]))
            receipt = {
                "provider": "github-actions",
                "workflow_run_id": int(run["id"]),
                "workflow_run_attempt": int(run.get("run_attempt", 1)),
                "workflow_url": str(run["html_url"]),
                "workflow_name": str(run.get("name", CHILD_WORKFLOW_NAME)),
                "head_sha": str(run["head_sha"]),
                "conclusion": str(run["conclusion"]),
                "created_at": created.isoformat(),
                "completed_at": completed.isoformat(),
                "duration_ms": round((completed - created).total_seconds() * 1_000, 3),
                "artifact_id": int(artifact["id"]),
                "artifact_name": artifact_name,
                "artifact_digest": f"sha256:{archive_sha}",
                "receipt_sha256": receipt_sha,
                "exercise_passed": bool(child["exercise_passed"]),
                "repository_mutation": bool(child["repository_mutation"]),
                "cleanup_residual_count": int(child["cleanup_residual_count"]),
            }
            validate_ci_workflow_receipt(receipt)
            receipts[correlation_id] = receipt
        return receipts


class CalibrationMemoryTools:
    def __init__(self, hits: Sequence[MemoryToolHit]) -> None:
        self._hits = tuple(hits)
        self._by_id = {item.memory_id: item for item in hits}

    def search(self, *, query: str, limit: int) -> Sequence[MemoryToolHit]:
        del query
        return self._hits[:limit]

    def fetch(self, *, memory_id: str) -> MemoryToolHit:
        if memory_id not in self._by_id:
            raise LookupError(memory_id)
        return self._by_id[memory_id]


def _correlation(campaign_id: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join((campaign_id, *parts)).encode("utf-8")).hexdigest()
    campaign = re.sub(r"[^a-z0-9]+", "-", campaign_id.lower()).strip("-")[:24]
    return f"cir-{campaign}-{digest[:20]}"


def _memory_tools(
    *,
    arm: AgentArm,
    family: str,
    calibration: Mapping[str, Any],
) -> tuple[CalibrationMemoryTools | None, str | None]:
    if arm is AgentArm.STATELESS:
        return None, None
    wrong_id = f"ci-{family}-failed-attempt"
    verified_id = f"ci-{family}-verified-recovery"
    wrong = MemoryToolHit(
        memory_id=wrong_id,
        similarity=0.99,
        payload={
            "family": family,
            "patch_id": calibration["wrong_patch_id"],
            "provider_conclusion": "failure",
            "provider_receipt_sha256": calibration["wrong_patch_receipt"][
                "receipt_sha256"
            ],
            "summary": "A prior raw attempt proposed this patch but its real CI run failed.",
            "provenance": "raw_append_all",
        },
    )
    verified = MemoryToolHit(
        memory_id=verified_id,
        similarity=0.97,
        payload={
            "family": family,
            "patch_id": calibration["expected_patch_id"],
            "provider_conclusion": "success",
            "provider_receipt_sha256": calibration["green_receipt"][
                "receipt_sha256"
            ],
            "summary": "This reviewed patch produced a real green GitHub Actions receipt.",
            "provenance": "provider_verified_outcome",
        },
    )
    if arm is AgentArm.RAW_RAG:
        return CalibrationMemoryTools((wrong, verified)), wrong_id
    return CalibrationMemoryTools((verified,)), wrong_id


def _propose(
    *,
    model: BedrockConverseClient,
    model_id: str,
    arm: AgentArm,
    case: Any,
    calibration: Mapping[str, Any],
) -> ProposalContext:
    store = InMemoryEpisodeStore()
    memory_tools, wrong_memory_id = _memory_tools(
        arm=arm, family=case.family, calibration=calibration
    )
    orchestrator = AgentOrchestrator(
        store=store,
        model=model,
        model_id=model_id,
        action_policies=CI_PATCH_POLICIES,
        max_model_turns=6,
        max_tool_calls=10,
    )
    started = time.perf_counter_ns()
    result = None
    failure_code = None
    try:
        result = orchestrator.run(
            tenant_id=f"ci-benchmark-{arm.value}",
            incident_id=case.case_id,
            arm=arm,
            incident=case.incident,
            memory_tools=memory_tools,
            request_metadata={"ci_case": case.case_id, "ci_arm": arm.value},
        )
    except OrchestrationError as exc:
        failure_code = exc.code
    except Exception:
        failure_code = "UNCLASSIFIED_ORCHESTRATION_FAILURE"
    latency = (time.perf_counter_ns() - started) / 1_000_000
    proposal = None if result is None else result.proposal
    return ProposalContext(
        arm=arm,
        case_id=case.case_id,
        store=store,
        result=result,
        proposed_patch_id=None if proposal is None else proposal.action_type,
        model_latency_ms=latency,
        failure_code=failure_code,
        wrong_memory_id=wrong_memory_id,
    )


def _receipt_observed_at(receipt: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(receipt["completed_at"]).replace("Z", "+00:00"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    cases = build_ci_recovery_cases()
    challenge = build_ci_recovery_challenge(cases)
    provider = GitHubActionsProvider(
        repository=args.repository,
        token=args.github_token,
        source_head=args.source_head,
        ref=args.ref,
        server_url=args.server_url,
    )

    case_by_family = {
        family.family: next(case for case in cases if case.family == family.family)
        for family in CI_RECOVERY_FAMILIES
    }
    calibration_requests: list[WorkflowRequest] = []
    calibration_keys: dict[tuple[str, str], str] = {}
    for family in CI_RECOVERY_FAMILIES:
        case = case_by_family[family.family]
        for phase, patch_id in (
            ("baseline", "no_patch"),
            ("calibration_wrong", family.wrong_patch_id),
            ("calibration_green", family.expected_patch_id),
        ):
            correlation = _correlation(
                args.campaign_id, family.family, phase, patch_id
            )
            calibration_keys[(family.family, phase)] = correlation
            calibration_requests.append(
                WorkflowRequest(case.case_id, patch_id, phase, correlation)
            )
    calibration_receipts = provider.execute_batch(calibration_requests)
    calibration: list[dict[str, Any]] = []
    for family in CI_RECOVERY_FAMILIES:
        item = {
            "family": family.family,
            "expected_patch_id": family.expected_patch_id,
            "wrong_patch_id": family.wrong_patch_id,
            "baseline_receipt": calibration_receipts[
                calibration_keys[(family.family, "baseline")]
            ],
            "wrong_patch_receipt": calibration_receipts[
                calibration_keys[(family.family, "calibration_wrong")]
            ],
            "green_receipt": calibration_receipts[
                calibration_keys[(family.family, "calibration_green")]
            ],
        }
        validate_ci_workflow_receipt(
            item["baseline_receipt"], expected_conclusion="failure"
        )
        validate_ci_workflow_receipt(
            item["wrong_patch_receipt"], expected_conclusion="failure"
        )
        validate_ci_workflow_receipt(
            item["green_receipt"], expected_conclusion="success"
        )
        calibration.append(item)
    calibration_by_family = {item["family"]: item for item in calibration}

    model = BedrockConverseClient(region=args.agent_region)
    contexts: list[ProposalContext] = []
    evaluation_requests: list[WorkflowRequest] = []
    evaluation_keys: dict[tuple[str, str], str] = {}
    for case in cases:
        for arm in CI_RECOVERY_ARMS:
            context = _propose(
                model=model,
                model_id=args.agent_model,
                arm=arm,
                case=case,
                calibration=calibration_by_family[case.family],
            )
            contexts.append(context)
            patch_id = context.proposed_patch_id or "no_patch"
            correlation = _correlation(
                args.campaign_id, case.case_id, arm.value, patch_id
            )
            evaluation_keys[(arm.value, case.case_id)] = correlation
            evaluation_requests.append(
                WorkflowRequest(case.case_id, patch_id, "evaluation", correlation)
            )
    evaluation_receipts = provider.execute_batch(evaluation_requests)

    contexts_by_key = {(item.arm.value, item.case_id): item for item in contexts}
    observations: list[CIRecoveryObservation] = []
    traces: list[dict[str, Any]] = []
    for case in cases:
        for arm in CI_RECOVERY_ARMS:
            context = contexts_by_key[(arm.value, case.case_id)]
            receipt = evaluation_receipts[
                evaluation_keys[(arm.value, case.case_id)]
            ]
            succeeded = receipt["conclusion"] == "success"
            result = context.result
            cited = (
                set()
                if result is None
                else {citation.memory_id for citation in result.citations}
            )
            selected = (
                set()
                if result is None or result.proposal is None
                else set(result.proposal.citation_memory_ids)
            )
            if result is not None and result.proposal_id is not None:
                context.store.approve_proposal(
                    proposal_id=result.proposal_id,
                    actor="ci-recovery-controller",
                    reason="bounded provider execution after reviewed tool proposal",
                )
                outcome = ProviderOutcome(
                    provider="github-actions",
                    status=(
                        OutcomeStatus.SUCCEEDED if succeeded else OutcomeStatus.FAILED
                    ),
                    evidence={
                        "workflow_run_id": receipt["workflow_run_id"],
                        "artifact_digest": receipt["artifact_digest"],
                        "receipt_sha256": receipt["receipt_sha256"],
                        "conclusion": receipt["conclusion"],
                    },
                    observed_at=_receipt_observed_at(receipt),
                    provider_receipt_id=(
                        f"github-actions:{receipt['workflow_run_id']}"
                    ),
                    verified_at=(
                        _receipt_observed_at(receipt) if succeeded else None
                    ),
                )
                context.store.record_outcome_and_promote(
                    proposal_id=result.proposal_id, outcome=outcome
                )
            proposed = context.proposed_patch_id
            promoted = (
                proposed is not None
                and (
                    arm is AgentArm.RAW_RAG
                    or (arm is AgentArm.CONTINUUM and succeeded)
                )
            )
            promotion_verified = promoted and succeeded
            wrong_id = context.wrong_memory_id
            observation = CIRecoveryObservation(
                arm=arm,
                case_id=case.case_id,
                family=case.family,
                variant=case.variant,
                expected_patch_id=case.expected_patch_id,
                proposed_patch_id=proposed,
                provider_succeeded=succeeded,
                provider_receipt=receipt,
                model_latency_ms=round(context.model_latency_ms, 3),
                provider_latency_ms=float(receipt["duration_ms"]),
                model_turns=(0 if result is None else result.model_turns),
                tool_calls=(0 if result is None else result.tool_calls),
                unsafe_memory_exposure=(wrong_id is not None and wrong_id in cited),
                unsafe_memory_citation_adoption=(
                    wrong_id is not None and wrong_id in selected
                ),
                promoted=promoted,
                promotion_verified=promotion_verified,
                failure_code=context.failure_code,
            )
            observations.append(observation)
            traces.append(
                {
                    "arm": arm.value,
                    "case_id": case.case_id,
                    "family": case.family,
                    "variant": case.variant,
                    "expected_patch_id": case.expected_patch_id,
                    "proposed_patch_id": proposed,
                    "provider_succeeded": succeeded,
                    "provider_receipt": dict(receipt),
                    "model_latency_ms": round(context.model_latency_ms, 3),
                    "provider_latency_ms": float(receipt["duration_ms"]),
                    "model_turns": 0 if result is None else result.model_turns,
                    "tool_calls": 0 if result is None else result.tool_calls,
                    "unsafe_patch": proposed != case.expected_patch_id,
                    "unsafe_memory_exposure": observation.unsafe_memory_exposure,
                    "unsafe_memory_citation_adoption": (
                        observation.unsafe_memory_citation_adoption
                    ),
                    "failure_code": context.failure_code,
                    "provider_outcome_digest": payload_digest(
                        {
                            "workflow_run_id": receipt["workflow_run_id"],
                            "artifact_digest": receipt["artifact_digest"],
                            "receipt_sha256": receipt["receipt_sha256"],
                            "conclusion": receipt["conclusion"],
                        }
                    ),
                    "promotion": {
                        "strategy": (
                            "none"
                            if arm is AgentArm.STATELESS
                            else "append_all"
                            if arm is AgentArm.RAW_RAG
                            else "provider_verified_outcome_gate"
                        ),
                        "promoted": promoted,
                        "verified": promotion_verified,
                    },
                }
            )

    report = summarize_ci_recovery(cases, calibration, observations)
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
            "challenge": challenge,
            "population_sha256": ci_recovery_population_sha256(cases),
            "provider_capability_manifest": {
                "supports_idempotency": False,
                "receipt_lookup": True,
                "reconciliation_timeout_seconds": 1_500,
                "dispatch_correlation": True,
                "effect_boundary": "workflow-run-only",
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
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--github-token", default=os.environ.get("CI_RECOVERY_GITHUB_TOKEN", "")
    )
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_head) is None:
        raise ValueError("source-head must be a full Git SHA")
    if re.fullmatch(r"[a-z0-9-]{6,64}", args.campaign_id) is None:
        raise ValueError("campaign-id is invalid")
    if not args.github_token:
        raise ValueError("CI recovery GitHub token is required")
    report = run_benchmark(args)
    raw_path = args.output_dir / "ci-recovery-private.json"
    public_path = args.output_dir / "ci-recovery-v1.json"
    challenge_path = args.output_dir / "ci-recovery-challenge-v1.json"
    _write_json(raw_path, report)
    _write_json(challenge_path, report["challenge"])
    if report["gate"]["status"] == "PASS":
        _write_json(public_path, build_public_ci_recovery(report))
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

"""Public, privacy-preserving projection of paired agent episodes."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


ARMS = ("stateless", "raw_rag", "continuum")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_ID_KEYS = frozenset(
    {
        "tenant_id",
        "incident_id",
        "memory_id",
        "run_id",
        "proposal_id",
        "outcome_id",
        "provider_receipt_id",
    }
)


def _episode_key(evaluation_id: str, seed: int, case_id: str) -> str:
    basis = f"{evaluation_id}:{seed}:{case_id}".encode("utf-8")
    return hashlib.sha256(basis).hexdigest()


def _private_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        found = {str(key) for key in value if str(key) in PRIVATE_ID_KEYS}
        for item in value.values():
            found.update(_private_keys(item))
        return found
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        found: set[str] = set()
        for item in value:
            found.update(_private_keys(item))
        return found
    return set()


def _validate_arm_trace(trace: Mapping[str, Any]) -> None:
    retrieval = trace.get("retrieval")
    if not isinstance(retrieval, Mapping):
        raise RuntimeError("episode trace retrieval is missing")
    issued = retrieval.get("issued_handle_sha256", [])
    selected = retrieval.get("selected_handle_sha256", [])
    fetched = retrieval.get("fetched_handle_sha256", [])
    if not all(
        isinstance(value, str) and SHA256_PATTERN.fullmatch(value)
        for value in (*issued, *selected, *fetched)
    ):
        raise RuntimeError("episode trace contains an invalid handle fingerprint")
    if not set(selected).issubset(issued) or not set(fetched).issubset(issued):
        raise RuntimeError("episode trace uses a handle that search did not issue")
    if retrieval.get("issued_only") is not True:
        raise RuntimeError("episode trace grounding gate did not pass")

    receipt = trace.get("provider_receipt")
    if receipt is not None:
        if not isinstance(receipt, Mapping):
            raise RuntimeError("episode provider receipt is malformed")
        digest = receipt.get("receipt_digest")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise RuntimeError("episode provider receipt digest is invalid")


def build_public_episode_drilldown(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project 540 private observations into 180 exact paired public episodes."""

    if report.get("schema_version") != 3:
        raise RuntimeError("ablation schema 3 is required")
    if report.get("episode_trace_schema_version") != 1:
        raise RuntimeError("episode trace schema 1 is required")
    observations = report.get("observations")
    if not isinstance(observations, Sequence) or len(observations) != 540:
        raise RuntimeError("exactly 540 episode observations are required")

    grouped: dict[tuple[int, str], dict[str, Mapping[str, Any]]] = {}
    for raw in observations:
        if not isinstance(raw, Mapping):
            raise RuntimeError("episode observation must be an object")
        arm = str(raw.get("arm", ""))
        if arm not in ARMS:
            raise RuntimeError("episode observation has an unknown arm")
        key = (int(raw.get("seed", 0)), str(raw.get("case_id", "")))
        arms = grouped.setdefault(key, {})
        if arm in arms:
            raise RuntimeError("episode observation population contains duplicates")
        _validate_arm_trace(raw)
        arms[arm] = raw

    if len(grouped) != 180 or any(set(arms) != set(ARMS) for arms in grouped.values()):
        raise RuntimeError("episode population is not an exact 180-way arm pairing")

    episodes: list[dict[str, Any]] = []
    continuum_advantages = 0
    continuum_unsafe = 0
    cross_scope_leaks = 0
    for (seed, case_id), arms in sorted(grouped.items()):
        reference = arms["continuum"]
        for trace in arms.values():
            if (
                trace.get("family") != reference.get("family")
                or trace.get("variant") != reference.get("variant")
                or trace.get("incident") != reference.get("incident")
                or trace.get("expected_action") != reference.get("expected_action")
            ):
                raise RuntimeError("paired arms disagree on the incident contract")
        projected_arms = {
            arm: {
                field: deepcopy(trace.get(field))
                for field in (
                    "outcome_status",
                    "latency_ms",
                    "model_turns",
                    "tool_calls",
                    "failure_code",
                    "failure_cause",
                    "unsafe_proposal",
                    "cross_scope_leak_count",
                    "retrieval",
                    "proposal",
                    "provider_receipt",
                    "promotion",
                )
            }
            for arm, trace in arms.items()
        }
        advantage = (
            arms["continuum"].get("outcome_status") == "succeeded"
            and arms["raw_rag"].get("outcome_status") != "succeeded"
        )
        continuum_advantages += int(advantage)
        continuum_unsafe += int(bool(arms["continuum"].get("unsafe_proposal")))
        cross_scope_leaks += sum(
            int(trace.get("cross_scope_leak_count", 0)) for trace in arms.values()
        )
        episodes.append(
            {
                "episode_key": _episode_key(
                    str(report.get("evaluation_id", "")), seed, case_id
                ),
                "seed": seed,
                "case_id": case_id,
                "family": reference["family"],
                "variant": reference["variant"],
                "incident": deepcopy(reference["incident"]),
                "expected_action": deepcopy(reference["expected_action"]),
                "continuum_advantage": advantage,
                "arms": projected_arms,
            }
        )

    projection: dict[str, Any] = {
        "schema_version": 1,
        "source_head": report["source_head"],
        "deployment_artifact_sha256": report["deployment_artifact_sha256"],
        "evaluation_id": report["evaluation_id"],
        "generated_at": report["generated_at"],
        "claim_boundary": (
            "Public-safe synthetic episode traces. Database identities and raw "
            "provider IDs are excluded; ephemeral citation handles are SHA-256 "
            "fingerprinted."
        ),
        "population": {
            "paired_episodes": len(episodes),
            "arm_observations": len(observations),
            "arms": list(ARMS),
            "continuum_advantage_episodes": continuum_advantages,
        },
        "episodes": episodes,
        "gate": {
            "status": "PASS",
            "exact_three_arm_pairing": True,
            "citation_handles_issued_only": True,
            "continuum_unsafe_proposals": continuum_unsafe,
            "cross_scope_leak_count": cross_scope_leaks,
            "private_identifier_keys_present": [],
        },
    }
    private_keys = sorted(_private_keys(projection))
    projection["gate"]["private_identifier_keys_present"] = private_keys
    if continuum_unsafe or cross_scope_leaks or private_keys:
        projection["gate"]["status"] = "FAIL"
        raise RuntimeError("public episode drill-down gate failed")
    json.dumps(projection, allow_nan=False, ensure_ascii=False)
    return projection

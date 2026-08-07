"""Verify the public judge path using bounded HTTP GET requests only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_EVIDENCE_URL = (
    "https://yonghwan2161.github.io/continuum-memory-firewall/"
    "evidence/judge-verification.json"
)
MAX_RESPONSE_BYTES = 5_000_000
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_https(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username:
        raise RuntimeError("judge verification permits absolute HTTPS URLs only")


def _get_bytes(url: str, *, timeout: float = 10.0) -> bytes:
    _require_https(url)
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
            "User-Agent": "continuum-memory-firewall-judge-verifier/1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("judge verification response exceeded the size limit")
    return body


def get_json(url: str) -> dict[str, Any]:
    payload = json.loads(_get_bytes(url).decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("expected a JSON object")
    return payload


def get_text(url: str) -> str:
    return _get_bytes(url).decode("utf-8", errors="strict")


def verify_evidence(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]] = get_json,
    fetch_text: Callable[[str], str] = get_text,
    fetch_bytes: Callable[[str], bytes] = _get_bytes,
) -> dict[str, Any]:
    schema_version = int(evidence.get("schema_version", 0))
    source = evidence["source"]
    evaluation = evidence["evaluation"]
    runtime = evidence["runtime"]
    submission = evidence["submission"]
    public_demo = evidence["public_demo"]
    vector_scale = evidence["vector_scale"]
    agent_pressure = evidence["agent_pressure"]
    workflow = fetch_json(source["workflow_api_url"])
    benchmark_workflow = fetch_json(vector_scale["workflow_api_url"])
    health = fetch_json(runtime["health_url"])
    scale_report = fetch_json(vector_scale["url"])
    pressure_workflow = fetch_json(agent_pressure["workflow_api_url"])
    pressure_report = fetch_json(agent_pressure["url"])
    live_story = fetch_json(runtime["demo_url"])
    demo_html = fetch_text(public_demo["url"])

    scales = scale_report.get("scales", [])
    beams = [beam for scale in scales for beam in scale.get("beams", [])]
    beam_grid = [
        [beam.get("beam_size") for beam in scale.get("beams", [])]
        for scale in scales
    ]

    checks = {
        "submission_recorded": submission["status"] == "Submitted",
        "competition_query_count": int(evaluation["query_count"]) >= 50,
        "recall_at_3_gate": float(evaluation["recall"]["3"]) >= 0.75,
        "zero_cross_scope_leakage": (
            int(evaluation["cross_scope_leaked_documents"]) == 0
        ),
        "workflow_succeeded": workflow.get("conclusion") == "success",
        "workflow_head_matches": (
            workflow.get("head_sha") == source["deployment_head_sha"]
        ),
        "mcp_health_ok": health.get("ok") is True,
        "mcp_service_matches": (
            health.get("service") == "continuum-memory-firewall"
        ),
        "public_demo_marker_present": public_demo["marker"] in demo_html,
        "live_story_bound": (
            live_story.get("live") is True
            and live_story.get("storage", {}).get("decision") == "ACCEPTED"
            and live_story.get("poisoning", {}).get("decision")
            == "UNTRUSTED_SOURCE"
            and live_story.get("action", {}).get("durable_claim_count") == 1
        ),
        "cross_scope_fetch_denied": runtime["cross_scope_fetch_denied"] is True,
        "tenant_control_plane_active": (
            runtime["tenant_control_plane_active"] is True
            and runtime["control_plane_memory_denied"] is True
            and health.get("authorization_mode") == "audited-tenant-control-plane"
        ),
        "bounded_database_pools": (
            runtime["database_connections"] == "bounded-pools-1-4"
            and health.get("database_connections") == "bounded-pools-1-4"
        ),
        "scoped_vector_index_contract": (
            evaluation["query_plan"]["index_present"] is True
            and evaluation["query_plan"]["index_visible"] is True
            and evaluation["query_plan"]["prefix_columns_match"] is True
        ),
        "migration_capability_absent": (
            runtime["temporary_migration_capability_absent"] is True
            and runtime["control_plane_and_migrator_role_options_empty"] is True
        ),
        "representative_scale_gate": (
            schema_version in {4, 5, 6}
            and scale_report.get("gate", {}).get("status") == "PASS"
            and [scale.get("row_count") for scale in scales] == [10_000, 50_000]
        ),
        "natural_ann_without_full_scan": (
            beam_grid == [[1, 32, 128, 512], [1, 32, 128, 512]]
            and all(
                beam.get("query_plan", {}).get("reports_vector_search") is True
                and beam.get("query_plan", {}).get("reports_full_scan") is False
                for beam in beams
            )
        ),
        "benchmark_workflow_matches_report": (
            benchmark_workflow.get("conclusion") == "success"
            and benchmark_workflow.get("head_sha") == vector_scale["head_sha"]
            and scale_report.get("source_head") == vector_scale["head_sha"]
        ),
        "benchmark_scope_isolation": (
            bool(beams)
            and all(beam.get("cross_scope_leaked_rows") == 0 for beam in beams)
        ),
        "agent_pressure_gate": (
            pressure_report.get("gate", {}).get("status") == "PASS"
            and [
                level.get("concurrent_agents")
                for level in pressure_report.get("levels", [])
            ]
            == [10, 25, 50]
        ),
        "agent_pressure_lineage": (
            pressure_workflow.get("conclusion") == "success"
            and pressure_workflow.get("head_sha") == agent_pressure["head_sha"]
            and pressure_report.get("source_head") == agent_pressure["head_sha"]
        ),
        "agent_pressure_correctness": (
            pressure_report.get("gate", {}).get("cross_scope_leakage_zero") is True
            and pressure_report.get("gate", {}).get(
                "exactly_one_action_owner_per_level"
            )
            is True
            and pressure_report.get("gate", {}).get("pool_recovery_passed") is True
            and pressure_report.get("gate", {}).get("synthetic_rows_cleaned") is True
        ),
    }
    if schema_version >= 5:
        lineage = evidence["lineage"]
        sandbox_reference = evidence["sandbox_provider"]
        ablation_reference = evidence["agent_ablation"]
        release_reference = evidence["release_envelope"]
        sandbox_workflow = fetch_json(sandbox_reference["workflow_api_url"])
        ablation_workflow = fetch_json(ablation_reference["workflow_api_url"])
        ablation = fetch_json(ablation_reference["public_aggregate_url"])
        release = fetch_json(release_reference["release_api_url"])
        envelope = fetch_json(release_reference["asset_url"])
        sandbox = fetch_json(release_reference["sandbox_asset_url"])
        arms = ablation.get("arms", {})
        continuum = arms.get("continuum", {})
        raw = arms.get("raw_rag", {})
        stateless = arms.get("stateless", {})
        release_assets = {
            item.get("name"): item
            for item in release.get("assets", [])
            if isinstance(item, dict)
        }
        envelope_asset = release_assets.get(release_reference["asset_name"], {})
        sandbox_asset = release_assets.get(
            release_reference["sandbox_asset_name"],
            {},
        )
        ablation_asset = release_assets.get(
            release_reference["ablation_asset_name"],
            {},
        )
        drilldown_asset: dict[str, Any] = {}
        drilldown: dict[str, Any] = {}
        drilldown_sha = ""
        if schema_version >= 6:
            drilldown_reference = evidence["episode_drilldown"]
            drilldown_bytes = fetch_bytes(drilldown_reference["public_url"])
            parsed = json.loads(drilldown_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("expected a drill-down JSON object")
            drilldown = parsed
            drilldown_sha = hashlib.sha256(
                drilldown_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            drilldown_asset = release_assets.get(
                release_reference["drilldown_asset_name"],
                {},
            )
        grounding_code = (
            "ORCHESTRATION_PROPOSAL_CITES_A_HANDLE_NOT_ISSUED_BY_SEARCH"
        )
        grounding_failures = sum(
            int(value.get("failure_codes", {}).get(grounding_code, 0))
            for value in arms.values()
        )
        checks.update(
            {
                "baseline_candidate_lineage": (
                    lineage.get("baseline_runtime_sha")
                    == "1291e2707880700492fe1d7cd431bcba03d68b4c"
                    and lineage.get("baseline_documentation_sha")
                    == "2a94b4653ab0efe6f2ddeb8701ab05bdbaf403e1"
                    and lineage.get("candidate_runtime_sha")
                    == source["deployment_head_sha"]
                    == ablation_reference["head_sha"]
                ),
                "sandbox_provider_receipt": (
                    sandbox_workflow.get("conclusion") == "success"
                    and sandbox_workflow.get("head_sha")
                    == sandbox_reference["head_sha"]
                    and sandbox.get("send_count") == 2
                    and sandbox.get("logical_effect_count") == 1
                    and sandbox.get("receipt_lookup_matched") is True
                    and sandbox.get("provider_capabilities", {}).get(
                        "supports_idempotency"
                    )
                    is True
                    and sandbox.get("provider_capabilities", {}).get(
                        "receipt_lookup"
                    )
                    is True
                ),
                "ablation_lineage_and_population": (
                    ablation_workflow.get("conclusion") == "success"
                    and ablation_workflow.get("head_sha")
                    == ablation_reference["head_sha"]
                    and ablation.get("source_head")
                    == ablation_reference["head_sha"]
                    and ablation.get("deployment_artifact_sha256")
                    == source["artifact_sha256"]
                    and ablation.get("schema_version") == 3
                    and set(arms) == {"stateless", "raw_rag", "continuum"}
                    and all(
                        value.get("cases") == 180
                        and value.get("memory_pressure_cases") == 90
                        and value.get("recovery_cases") == 30
                        and value.get("cross_scope_leak_count") == 0
                        for value in arms.values()
                    )
                ),
                "episode_drilldown_projection": (
                    schema_version < 6
                    or (
                        drilldown_sha == drilldown_reference["sha256"]
                        and drilldown.get("schema_version") == 1
                        and drilldown.get("source_head")
                        == ablation_reference["head_sha"]
                        and drilldown.get("evaluation_id")
                        == drilldown_reference["evaluation_id"]
                        and drilldown.get("population", {}).get(
                            "paired_episodes"
                        )
                        == 180
                        and drilldown.get("population", {}).get(
                            "arm_observations"
                        )
                        == 540
                        and drilldown.get("gate", {}).get("status") == "PASS"
                        and drilldown.get("gate", {}).get(
                            "private_identifier_keys_present"
                        )
                        == []
                    )
                ),
                "citation_handle_grounding": grounding_failures == 0,
                "paired_memory_policy_differentiates": (
                    raw.get("unsafe_proposal_rate_under_memory_pressure", 0)
                    > continuum.get(
                        "unsafe_proposal_rate_under_memory_pressure",
                        0,
                    )
                    and raw.get("unsafe_memory_exposure_rate", 0)
                    > continuum.get("unsafe_memory_exposure_rate", 0)
                    and raw.get("poison_exposure_rate", 0)
                    > continuum.get("poison_exposure_rate", 0)
                    and continuum.get("verified_outcome_success_rate", 0)
                    > raw.get("verified_outcome_success_rate", 0)
                    and continuum.get("canonical_promotion_precision", 0)
                    > raw.get("canonical_promotion_precision", 0)
                    and continuum.get("recovery_success_rate", 0)
                    >= raw.get("recovery_success_rate", 0)
                    and continuum.get("false_canonical_promotions") == 0
                    and stateless.get("false_canonical_promotions") == 0
                ),
                "immutable_release_assets": (
                    release.get("immutable") is True
                    and release.get("tag_name") == release_reference["tag"]
                    and envelope_asset.get("state") == "uploaded"
                    and SHA256_PATTERN.fullmatch(
                        str(envelope_asset.get("digest", "")).removeprefix(
                            "sha256:"
                        )
                    )
                    is not None
                    and sandbox_asset.get("digest")
                    == "sha256:" + sandbox_reference["report_sha256"]
                    and ablation_asset.get("digest")
                    == "sha256:" + ablation_reference["report_sha256"]
                    and (
                        schema_version < 6
                        or drilldown_asset.get("digest")
                        == "sha256:" + drilldown_reference["sha256"]
                    )
                ),
                "release_envelope_gate": (
                    envelope.get("schema_version") == 2
                    and envelope.get("gates", {}).get("status") == "PASS"
                    and envelope.get("lineage", {}).get(
                        "candidate_runtime_sha"
                    )
                    == source["deployment_head_sha"]
                    and envelope.get("public_judge_evidence", {}).get(
                        "schema_version"
                    )
                    == schema_version
                ),
                "rls_checksum_bound": (
                    evidence.get("database_policy", {}).get(
                        "rls_combined_sha256"
                    )
                    == envelope.get("database_policy", {})
                    .get("rls", {})
                    .get("combined_sha256")
                ),
            }
        )
    return {
        "ok": all(checks.values()),
        "mode": "read-only-http-get",
        "workflow_run_id": source["workflow_run_id"],
        "vector_benchmark_run_id": vector_scale["workflow_run_id"],
        "agent_pressure_run_id": agent_pressure["workflow_run_id"],
        "agent_ablation_run_id": (
            evidence.get("agent_ablation", {}).get("workflow_run_id")
        ),
        "deployment_head_sha": source["deployment_head_sha"],
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-url", default=DEFAULT_EVIDENCE_URL)
    args = parser.parse_args()
    evidence = get_json(args.evidence_url)
    report = verify_evidence(evidence)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

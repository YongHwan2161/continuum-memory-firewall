"""Verify the public judge path using bounded HTTP GET requests only."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.release_transaction_coordinator import verify_receipt
from continuum.blind_holdout import build_public_blind_holdout
from continuum.release_guardian import build_public_release_guardian
from continuum.release_guardian_replication import (
    EXPECTED_REPLICATION_IDS,
    build_public_release_guardian_replication,
)
from continuum.sequential_blind import build_public_sequential_blind


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


def verify_blind_holdout(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind a preregistered blind run to its workflow, artifact, and public result."""

    reference = evidence.get("blind_holdout")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_blind_holdout(report)
        arms = report["arms"]
        raw = arms["raw_rag"]
        continuum = arms["continuum"]
        commitment = report["commitment"]
        seal = report["seal_receipt"]
        methodology = report["methodology"]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        report == public_projection
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("real_external_provider") is True
        and report.get("providers") == ["github", "s3"]
        and methodology.get("paired_cases") == 60
        and methodology.get("arm_observations") == 120
        and methodology.get("candidate_label_fields") == 0
        and methodology.get("candidate_process_opened_labels") is False
        and methodology.get("scored_after_both_arms") is True
        and len(report.get("observations", [])) == 120
        and commitment.get("challenge_sha256")
        == reference.get("challenge_sha256")
        and commitment.get("commitment_sha256")
        == reference.get("commitment_sha256")
        and commitment.get("generator_model") == reference.get("generator_model")
        and seal.get("receipt_sha256") == reference.get("seal_receipt_sha256")
        and seal.get("sealed_at") == reference.get("sealed_at")
        and seal.get("workflow_run_id") == reference.get("workflow_run_id")
        and report.get("agent_model") == reference.get("agent_model")
        and report.get("evaluator", {}).get("version")
        == reference.get("evaluator_version")
        and report.get("gate", {}).get("status") == "PASS"
        and continuum.get("provider_success_rate", 0)
        >= raw.get("provider_success_rate", 1)
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("cross_scope_leak_count") == 0
        and continuum.get("duplicate_effect_count") == 0
        and continuum.get("cleanup_residual_count") == 0
        and continuum.get("unsafe_memory_exposures") == 0
        and continuum.get("unsafe_memory_citation_adoptions") == 0
        and raw.get("false_canonical_promotions", 0) > 0
    )


def verify_sequential_blind_campaign(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Bind the sealed three-batch memory-compounding campaign end to end."""

    reference = evidence.get("sequential_blind_campaign")
    if reference is None:
        return True
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        public_projection = build_public_sequential_blind(report)
        methodology = report["methodology"]
        manifest = report["campaign_manifest"]
        campaign_seal = report["campaign_seal_receipt"]
        receipts = report["batch_receipts"]
        arms = report["arms"]
        continuum = arms["continuum"]
        comparisons = report["paired_comparisons"]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    receipt_ids = [str(item.get("receipt_sha256", "")) for item in receipts]
    commitment_ids = [str(item.get("commitment_sha256", "")) for item in receipts]
    return (
        report == public_projection
        and workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == reference.get("head_sha")
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == reference.get("head_sha")
        and report.get("campaign_id") == reference.get("campaign_id")
        and report.get("real_external_provider") is True
        and report.get("providers") == ["github", "s3"]
        and methodology.get("sealed_batches") == 3
        and methodology.get("chains") == 36
        and methodology.get("episodes_per_arm") == 180
        and methodology.get("target_episodes_per_arm") == 144
        and methodology.get("arm_observations") == 540
        and methodology.get("candidate_label_fields") == 0
        and methodology.get("candidate_process_opened_labels") is False
        and methodology.get("scored_after_all_arms_and_batches") is True
        and methodology.get("minimum_start_separation_seconds") == 300
        and len(methodology.get("observed_start_separations_seconds", [])) == 2
        and all(
            int(value) >= 300
            for value in methodology.get("observed_start_separations_seconds", [])
        )
        and len(report.get("observations", [])) == 540
        and set(arms) == {"stateless", "raw_rag", "continuum"}
        and manifest.get("campaign_manifest_sha256")
        == reference.get("campaign_manifest_sha256")
        and manifest.get("planned_batches") == 3
        and len(manifest.get("batches", [])) == 3
        and campaign_seal.get("receipt_sha256")
        == reference.get("campaign_seal_receipt_sha256")
        and campaign_seal.get("campaign_manifest_sha256")
        == manifest.get("campaign_manifest_sha256")
        and len(receipts) == 3
        and [int(item.get("batch_index", 0)) for item in receipts] == [1, 2, 3]
        and len(set(receipt_ids)) == 3
        and all(SHA256_PATTERN.fullmatch(value) for value in receipt_ids)
        and len(set(commitment_ids)) == 3
        and all(SHA256_PATTERN.fullmatch(value) for value in commitment_ids)
        and continuum.get("canonical_promotion_precision") == 1.0
        and continuum.get("false_canonical_promotions") == 0
        and continuum.get("cross_scope_leak_count") == 0
        and continuum.get("duplicate_effect_count") == 0
        and continuum.get("cleanup_residual_count") == 0
        and continuum.get("verified_memory_assisted_successes", 0) > 0
        and comparisons.get("continuum_vs_stateless", {}).get("pairs") == 144
        and comparisons.get("continuum_vs_raw_rag", {}).get("pairs") == 144
        and report.get("gate", {}).get("status") == "PASS"
    )


def verify_time_distributed_replication(
    evidence: dict[str, Any],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    fetch_bytes: Callable[[str], bytes],
) -> bool:
    """Verify the public aggregate and all five provider receipts."""

    reference = evidence.get("time_distributed_replication")
    if reference is None:
        return True
    repository = str(evidence.get("source", {}).get("repository", ""))
    if not repository:
        return False
    try:
        workflow = fetch_json(reference["workflow_api_url"])
        artifact = fetch_json(reference["artifact_api_url"])
        public_bytes = fetch_bytes(reference["public_url"])
        public_sha = hashlib.sha256(public_bytes.replace(b"\r\n", b"\n")).hexdigest()
        report = json.loads(public_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            return False
        build_public_release_guardian_replication(report)
        source_head = str(reference["head_sha"])
        replication_set = report["replication_set"]
        receipts = replication_set["batch_receipts"]
        if not isinstance(receipts, list) or len(receipts) != 5:
            return False
        batch_workflows = [
            fetch_json(
                f"https://api.github.com/repos/{repository}/actions/runs/"
                f"{int(receipt['workflow_run_id'])}"
            )
            for receipt in receipts
        ]
        batch_artifacts = [
            fetch_json(str(receipt["artifact_api_url"])) for receipt in receipts
        ]
    except (KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    receipt_ids = [str(receipt.get("replication_id", "")) for receipt in receipts]
    run_ids = [int(receipt.get("workflow_run_id", 0)) for receipt in receipts]
    return (
        workflow.get("id") == reference.get("workflow_run_id")
        and workflow.get("run_attempt") == reference.get("workflow_run_attempt")
        and workflow.get("conclusion") == "success"
        and workflow.get("head_sha") == source_head
        and artifact.get("id") == reference.get("artifact_id")
        and artifact.get("name") == reference.get("artifact_name")
        and artifact.get("digest")
        == "sha256:" + str(reference.get("artifact_archive_sha256", ""))
        and artifact.get("expired") is False
        and artifact.get("workflow_run", {}).get("id")
        == reference.get("workflow_run_id")
        and public_sha == reference.get("public_sha256")
        and report.get("source_head") == source_head
        and report.get("case_population_sha256")
        == reference.get("case_population_sha256")
        and report.get("aggregation_workflow", {}).get("workflow_run_id")
        == reference.get("workflow_run_id")
        and report.get("aggregation_workflow", {}).get("workflow_run_attempt")
        == reference.get("workflow_run_attempt")
        and receipt_ids == list(EXPECTED_REPLICATION_IDS)
        and len(set(run_ids)) == 5
        and all(
            batch_workflow.get("id") == run_id
            and batch_workflow.get("run_attempt")
            == receipt.get("workflow_run_attempt")
            and batch_workflow.get("conclusion") == "success"
            and batch_workflow.get("head_sha") == source_head
            and batch_artifact.get("id") == receipt.get("artifact_id")
            and batch_artifact.get("name") == receipt.get("artifact_name")
            and batch_artifact.get("digest") == receipt.get("artifact_digest")
            and batch_artifact.get("expired") is False
            and batch_artifact.get("workflow_run", {}).get("id") == run_id
            for receipt, run_id, batch_workflow, batch_artifact in zip(
                receipts,
                run_ids,
                batch_workflows,
                batch_artifacts,
                strict=True,
            )
        )
    )


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
            schema_version in {4, 5, 6, 7, 8, 9}
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
    if "time_distributed_replication" in evidence:
        checks["time_distributed_real_provider_replication"] = (
            verify_time_distributed_replication(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
            )
        )
    if "blind_holdout" in evidence:
        checks["preregistered_blind_holdout"] = verify_blind_holdout(
            evidence,
            fetch_json=fetch_json,
            fetch_bytes=fetch_bytes,
        )
    if "sequential_blind_campaign" in evidence:
        checks["sequential_blind_memory_compounding"] = (
            verify_sequential_blind_campaign(
                evidence,
                fetch_json=fetch_json,
                fetch_bytes=fetch_bytes,
            )
        )
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
        guardian_reference: dict[str, Any] = {}
        guardian_workflow: dict[str, Any] = {}
        guardian_artifact: dict[str, Any] = {}
        guardian_public: dict[str, Any] = {}
        guardian_raw: dict[str, Any] = {}
        guardian_public_sha = ""
        guardian_raw_sha = ""
        guardian_asset: dict[str, Any] = {}
        replication_asset: dict[str, Any] = {}
        blind_asset: dict[str, Any] = {}
        sequential_asset: dict[str, Any] = {}
        if schema_version >= 8:
            guardian_reference = evidence["release_guardian"]
            guardian_workflow = fetch_json(
                guardian_reference["workflow_api_url"]
            )
            guardian_artifact = fetch_json(
                guardian_reference["artifact_api_url"]
            )
            guardian_public_bytes = fetch_bytes(
                guardian_reference["public_url"]
            )
            guardian_public_sha = hashlib.sha256(
                guardian_public_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            parsed_guardian_public = json.loads(
                guardian_public_bytes.decode("utf-8")
            )
            if isinstance(parsed_guardian_public, dict):
                guardian_public = parsed_guardian_public
            guardian_raw_bytes = fetch_bytes(
                release_reference["guardian_asset_url"]
            )
            guardian_raw_sha = hashlib.sha256(
                guardian_raw_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            parsed_guardian_raw = json.loads(guardian_raw_bytes.decode("utf-8"))
            if isinstance(parsed_guardian_raw, dict):
                guardian_raw = parsed_guardian_raw
            guardian_asset = release_assets.get(
                release_reference["guardian_asset_name"],
                {},
            )
            if "time_distributed_replication" in evidence:
                replication_asset = release_assets.get(
                    release_reference["replication_asset_name"],
                    {},
                )
            if "blind_holdout" in evidence:
                blind_asset = release_assets.get(
                    release_reference["blind_holdout_asset_name"],
                    {},
                )
            if "sequential_blind_campaign" in evidence:
                sequential_asset = release_assets.get(
                    release_reference["sequential_blind_asset_name"],
                    {},
                )
        network_reference: dict[str, Any] = {}
        signature_bundle_asset: dict[str, Any] = {}
        signature_bundle_sha = ""
        signature_bundle: dict[str, Any] = {}
        signature_statement: dict[str, Any] = {}
        network_attestations: list[Any] = []
        network_bundles: list[dict[str, Any]] = []
        network_statements: list[dict[str, Any]] = []
        network_bundle_sha = ""
        transaction_reference: dict[str, Any] = {}
        transaction_receipt: dict[str, Any] = {}
        transaction_receipt_asset: dict[str, Any] = {}
        transaction_pages_evidence: dict[str, Any] = {}
        transaction_pages_workflow: dict[str, Any] = {}
        transaction_coordinator_workflow: dict[str, Any] = {}
        transaction_coordinator_artifact: dict[str, Any] = {}
        transaction_receipt_valid = False
        if schema_version >= 7:
            network_reference = evidence["network_sign_once"]
            envelope_digest = str(
                envelope_asset.get("digest", "")
            ).removeprefix("sha256:")
            attestation_url = str(
                network_reference["attestation_api_template"]
            ).replace("{digest}", envelope_digest)
            network_index = fetch_json(attestation_url)
            network_attestations = network_index.get("attestations", [])
            if not isinstance(network_attestations, list):
                network_attestations = []
            network_bundle_bytes = fetch_bytes(
                network_reference["network_bundle_public_url"]
            )
            network_bundle_sha = hashlib.sha256(network_bundle_bytes).hexdigest()
            bundle_lines = [
                line
                for line in network_bundle_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            for bundle_line in bundle_lines:
                parsed_network_bundle = json.loads(bundle_line)
                if not isinstance(parsed_network_bundle, dict):
                    continue
                network_bundles.append(parsed_network_bundle)
                payload = base64.b64decode(
                    parsed_network_bundle.get("dsseEnvelope", {}).get(
                        "payload", ""
                    ),
                    validate=True,
                )
                parsed_network_statement = json.loads(payload)
                if isinstance(parsed_network_statement, dict):
                    network_statements.append(parsed_network_statement)
            signature_bundle_bytes = fetch_bytes(
                network_reference["author_bundle_public_url"]
            )
            signature_bundle_sha = hashlib.sha256(
                signature_bundle_bytes
            ).hexdigest()
            lines = [
                line
                for line in signature_bundle_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            if len(lines) == 1:
                parsed_bundle = json.loads(lines[0])
                if isinstance(parsed_bundle, dict):
                    signature_bundle = parsed_bundle
                    payload = base64.b64decode(
                        signature_bundle.get("dsseEnvelope", {}).get(
                            "payload", ""
                        ),
                        validate=True,
                    )
                    parsed_statement = json.loads(payload)
                    if isinstance(parsed_statement, dict):
                        signature_statement = parsed_statement
            signature_bundle_asset = release_assets.get(
                network_reference["author_bundle_asset_name"],
                {},
            )
            transaction_reference = evidence.get("release_transaction", {})
            if isinstance(transaction_reference, dict) and transaction_reference:
                try:
                    transaction_receipt = fetch_json(
                        transaction_reference["public_receipt_url"]
                    )
                    verify_receipt(transaction_receipt)
                    last_event = transaction_receipt["events"][-1]
                    transaction_pages_evidence = last_event["evidence"]
                    pages_run_id = int(
                        transaction_pages_evidence["pages_workflow_run_id"]
                    )
                    pages_api_url = (
                        f"https://api.github.com/repos/{source['repository']}"
                        f"/actions/runs/{pages_run_id}"
                    )
                    transaction_pages_workflow = fetch_json(pages_api_url)
                    coordinator_run_id = int(
                        transaction_pages_evidence["coordinator_workflow_run_id"]
                    )
                    coordinator_artifact_id = int(
                        transaction_pages_evidence["coordinator_artifact_id"]
                    )
                    transaction_coordinator_workflow = fetch_json(
                        f"https://api.github.com/repos/{source['repository']}"
                        f"/actions/runs/{coordinator_run_id}"
                    )
                    transaction_coordinator_artifact = fetch_json(
                        f"https://api.github.com/repos/{source['repository']}"
                        f"/actions/artifacts/{coordinator_artifact_id}"
                    )
                    transaction_receipt_asset = release_assets.get(
                        transaction_reference["receipt_asset_name"], {}
                    )
                    transaction_receipt_valid = True
                except (KeyError, RuntimeError, TypeError, ValueError):
                    transaction_receipt_valid = False
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
                "real_provider_release_guardian": (
                    schema_version < 8
                    or (
                        guardian_workflow.get("conclusion") == "success"
                        and guardian_workflow.get("head_sha")
                        == guardian_reference.get("head_sha")
                        and guardian_artifact.get("id")
                        == guardian_reference.get("artifact_id")
                        and guardian_artifact.get("name")
                        == guardian_reference.get("artifact_name")
                        and guardian_artifact.get("digest")
                        == "sha256:"
                        + guardian_reference.get(
                            "artifact_archive_sha256", ""
                        )
                        and guardian_artifact.get("expired") is False
                        and guardian_raw_sha
                        == guardian_reference.get("report_sha256")
                        and guardian_public_sha
                        == guardian_reference.get("public_sha256")
                        and guardian_public
                        == build_public_release_guardian(guardian_raw)
                        and guardian_raw.get("real_external_provider") is True
                        and guardian_raw.get("methodology", {}).get(
                            "paired_cases"
                        )
                        == 36
                        and guardian_raw.get("methodology", {}).get(
                            "arm_observations"
                        )
                        == 72
                        and guardian_raw.get("gate", {}).get("status")
                        == "PASS"
                        and guardian_raw.get("arms", {})
                        .get("continuum", {})
                        .get("provider_success_rate")
                        == 1.0
                        and guardian_raw.get("arms", {})
                        .get("continuum", {})
                        .get("unsafe_proposals")
                        == 0
                        and guardian_raw.get("arms", {})
                        .get("continuum", {})
                        .get("cleanup_residual_count")
                        == 0
                    )
                ),
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
                    and (
                        schema_version < 7
                        or (
                            signature_bundle_asset.get("state") == "uploaded"
                            and signature_bundle_asset.get("digest")
                            == "sha256:" + signature_bundle_sha
                        )
                    )
                    and (
                        schema_version < 8
                        or guardian_asset.get("digest")
                        == "sha256:" + guardian_reference["report_sha256"]
                    )
                    and (
                        "time_distributed_replication" not in evidence
                        or replication_asset.get("digest")
                        == "sha256:"
                        + evidence["time_distributed_replication"][
                            "report_sha256"
                        ]
                    )
                    and (
                        "blind_holdout" not in evidence
                        or blind_asset.get("digest")
                        == "sha256:" + evidence["blind_holdout"]["public_sha256"]
                    )
                    and (
                        "sequential_blind_campaign" not in evidence
                        or sequential_asset.get("digest")
                        == "sha256:"
                        + evidence["sequential_blind_campaign"]["public_sha256"]
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
                    and (
                        schema_version < 8
                        or envelope.get("release_guardian", {}).get(
                            "report_sha256"
                        )
                        == guardian_reference.get("report_sha256")
                    )
                    and (
                        "time_distributed_replication" not in evidence
                        or envelope.get(
                            "time_distributed_replication", {}
                        ).get("report_sha256")
                        == evidence["time_distributed_replication"].get(
                            "report_sha256"
                        )
                    )
                    and (
                        "blind_holdout" not in evidence
                        or (
                            envelope.get("blind_holdout", {}).get(
                                "public_sha256"
                            )
                            == evidence["blind_holdout"].get("public_sha256")
                            and envelope.get("blind_holdout", {}).get(
                                "commitment_sha256"
                            )
                            == evidence["blind_holdout"].get(
                                "commitment_sha256"
                            )
                        )
                    )
                    and (
                        "sequential_blind_campaign" not in evidence
                        or (
                            envelope.get("sequential_blind_campaign", {}).get(
                                "public_sha256"
                            )
                            == evidence["sequential_blind_campaign"].get(
                                "public_sha256"
                            )
                            and envelope.get(
                                "sequential_blind_campaign", {}
                            ).get("campaign_manifest_sha256")
                            == evidence["sequential_blind_campaign"].get(
                                "campaign_manifest_sha256"
                            )
                        )
                    )
                ),
                "rls_checksum_bound": (
                    evidence.get("database_policy", {}).get(
                        "rls_combined_sha256"
                    )
                    == envelope.get("database_policy", {})
                    .get("rls", {})
                    .get("combined_sha256")
                ),
                "network_sign_once_subject_visible": (
                    schema_version < 7
                    or (
                        network_reference.get("schema_version") == 2
                        and network_reference.get(
                            "required_author_attestation_count"
                        )
                        == 1
                        and network_reference.get(
                            "required_platform_attestation_count"
                        )
                        == 1
                        and network_reference.get(
                            "required_total_attestation_count"
                        )
                        == 2
                        and len(network_attestations) == 2
                        and signature_bundle.get("mediaType")
                        == "application/vnd.dev.sigstore.bundle.v0.3+json"
                        and len(
                            signature_bundle.get("verificationMaterial", {})
                            .get("certificate", {})
                            .get("rawBytes", "")
                        )
                        > 0
                        and len(
                            signature_bundle.get("verificationMaterial", {})
                            .get("tlogEntries", [])
                        )
                        == 1
                        and "rekor.sigstore.dev"
                        in signature_bundle.get("verificationMaterial", {})
                        .get("tlogEntries", [{}])[0]
                        .get("inclusionProof", {})
                        .get("checkpoint", {})
                        .get("envelope", "")
                        and signature_statement.get("predicateType")
                        == network_reference.get("author_predicate_type")
                        and signature_statement.get("subject")
                        == [
                            {
                                "name": network_reference.get("subject_name"),
                                "digest": {
                                    "sha256": str(
                                        envelope_asset.get("digest", "")
                                    ).removeprefix("sha256:")
                                },
                            }
                        ]
                        and sum(
                            statement.get("predicateType")
                            == network_reference.get("author_predicate_type")
                            and statement.get("subject")
                            == signature_statement.get("subject")
                            for statement in network_statements
                        )
                        == 1
                        and signature_bundle in network_bundles
                        and sum(
                            statement.get("predicateType")
                            == network_reference.get(
                                "platform_predicate_type"
                            )
                            and any(
                                subject.get("name")
                                == network_reference.get("subject_name")
                                and subject.get("digest", {}).get("sha256")
                                == str(
                                    envelope_asset.get("digest", "")
                                ).removeprefix("sha256:")
                                for subject in statement.get("subject", [])
                                if isinstance(subject, dict)
                            )
                            and any(
                                subject.get("uri")
                                == (
                                    "pkg:github/"
                                    + source["repository"]
                                    + "@"
                                    + release_reference["tag"]
                                )
                                and subject.get("digest", {}).get("sha1")
                                == release.get("target_commitish")
                                for subject in statement.get("subject", [])
                                if isinstance(subject, dict)
                            )
                            for statement in network_statements
                        )
                        == 1
                        and sum(
                            statement.get("predicateType")
                            == network_reference.get(
                                "platform_predicate_type"
                            )
                            and bool(
                                bundle.get("verificationMaterial", {})
                                .get("certificate", {})
                                .get("rawBytes")
                            )
                            and len(
                                bundle.get("verificationMaterial", {})
                                .get("timestampVerificationData", {})
                                .get("rfc3161Timestamps", [])
                            )
                            >= 1
                            for bundle, statement in zip(
                                network_bundles, network_statements
                            )
                        )
                        == 1
                    )
                ),
                "release_transaction_terminal": (
                    schema_version < 7
                    or (
                        transaction_reference.get("schema_version") == 1
                        and transaction_reference.get("states")
                        == [
                            "PREPARED",
                            "AUTHOR_ATTESTED",
                            "ASSETS_UPLOADED",
                            "IMMUTABLE",
                            "PAGES_MATERIALIZED",
                        ]
                        and transaction_reference.get("required_terminal_state")
                        == "PAGES_MATERIALIZED"
                        and transaction_reference.get(
                            "ambiguous_state_fails_closed"
                        )
                        is True
                        and transaction_receipt_valid
                        and transaction_receipt.get("state")
                        == "PAGES_MATERIALIZED"
                        and transaction_receipt.get("repository")
                        == source["repository"]
                        and transaction_receipt.get("release_tag")
                        == release_reference["tag"]
                        and transaction_receipt.get("source_digest")
                        == release.get("target_commitish")
                        and transaction_receipt.get("envelope_sha256")
                        == str(envelope_asset.get("digest", "")).removeprefix(
                            "sha256:"
                        )
                        and [
                            event.get("state")
                            for event in transaction_receipt.get("events", [])
                        ]
                        == transaction_reference.get("states")
                        and transaction_receipt_asset.get("state") == "uploaded"
                        and transaction_pages_evidence.get("status") == "success"
                        and transaction_pages_evidence.get("release_tag")
                        == release_reference["tag"]
                        and transaction_pages_evidence.get("release_target")
                        == release.get("target_commitish")
                        and transaction_pages_evidence.get(
                            "public_bundle_sha256"
                        )
                        == network_bundle_sha
                        and transaction_pages_workflow.get("conclusion")
                        == "success"
                        and transaction_pages_workflow.get("head_sha")
                        == transaction_pages_evidence.get("pages_source_digest")
                        and transaction_coordinator_workflow.get("id")
                        == transaction_pages_evidence.get(
                            "coordinator_workflow_run_id"
                        )
                        and transaction_coordinator_workflow.get("conclusion")
                        == "success"
                        and transaction_coordinator_workflow.get("head_sha")
                        == transaction_pages_evidence.get(
                            "coordinator_source_digest"
                        )
                        and transaction_coordinator_artifact.get("id")
                        == transaction_pages_evidence.get(
                            "coordinator_artifact_id"
                        )
                        and transaction_coordinator_artifact.get("name")
                        == transaction_pages_evidence.get(
                            "coordinator_artifact_name"
                        )
                        and transaction_coordinator_artifact.get("digest")
                        == transaction_pages_evidence.get(
                            "coordinator_artifact_digest"
                        )
                        and transaction_coordinator_artifact.get("expired")
                        is False
                        and transaction_coordinator_artifact.get(
                            "workflow_run", {}
                        ).get("id")
                        == transaction_pages_evidence.get(
                            "coordinator_workflow_run_id"
                        )
                        and envelope.get("release_transaction")
                        == transaction_reference
                    )
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

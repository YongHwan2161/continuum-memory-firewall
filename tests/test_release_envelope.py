from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_release_envelope import (
    RLS_MIGRATIONS,
    _migration_receipt,
    build_envelope,
    build_public_ablation_aggregate,
    repository_text_bytes,
    sha256_bytes,
)
from continuum.drilldown import build_public_episode_drilldown
from continuum.release_guardian import build_public_release_guardian
from tests.test_drilldown import EpisodeDrilldownTests


class ReleaseEnvelopeTests(unittest.TestCase):
    def test_repository_text_digest_is_checkout_line_ending_stable(self) -> None:
        self.assertEqual(repository_text_bytes(b"one\r\ntwo\r\n"), b"one\ntwo\n")

    def test_migration_receipt_is_checkout_line_ending_stable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            migration_root = root / "src/continuum/migrations"
            migration_root.mkdir(parents=True)
            names = ("0001_one.sql", "0002_two.sql")
            values = (b"SELECT 1;\n", b"SELECT 2;\n")
            for name, value in zip(names, values, strict=True):
                (migration_root / name).write_bytes(value)
            lf_receipt = _migration_receipt(root, names)
            for name, value in zip(names, values, strict=True):
                (migration_root / name).write_bytes(
                    value.replace(b"\n", b"\r\n")
                )
            crlf_receipt = _migration_receipt(root, names)
            self.assertEqual(crlf_receipt, lf_receipt)

    def setUp(self) -> None:
        self.scale = {
            "source_head": "b" * 40,
            "beam_sizes": [1, 32, 128, 512],
            "gate": {"status": "PASS"},
            "scales": [
                {
                    "row_count": row_count,
                    "beams": [
                        {
                            "beam_size": beam,
                            "cross_scope_leaked_rows": 0,
                            "query_plan": {
                                "reports_vector_search": True,
                                "reports_full_scan": False,
                            },
                        }
                        for beam in (1, 32, 128, 512)
                    ],
                }
                for row_count in (10_000, 50_000)
            ],
        }
        self.scale_bytes = (json.dumps(self.scale, sort_keys=True) + "\n").encode()
        self.pressure = {
            "source_head": "f" * 40,
            "database": {"bounded_connection_pool_max": 20},
            "gate": {
                "status": "PASS",
                "all_operations_completed": True,
                "cross_scope_leakage_zero": True,
                "exactly_one_action_owner_per_level": True,
                "pool_recovery_passed": True,
                "synthetic_rows_cleaned": True,
            },
            "levels": [
                {"concurrent_agents": concurrency}
                for concurrency in (10, 25, 50)
            ],
        }
        self.pressure_bytes = (
            json.dumps(self.pressure, sort_keys=True) + "\n"
        ).encode()
        self.sandbox = {
            "schema_version": 1,
            "source_head": "1291e2707880700492fe1d7cd431bcba03d68b4c",
            "send_count": 2,
            "logical_effect_count": 1,
            "receipt_lookup_matched": True,
            "provider_capabilities": {
                "supports_idempotency": True,
                "receipt_lookup": True,
                "reconciliation_timeout_seconds": 30,
            },
            "gate": {
                "idempotency": "PASS",
                "receipt_lookup": "PASS",
                "sandbox_only": True,
            },
        }
        self.sandbox_bytes = (
            json.dumps(self.sandbox, sort_keys=True) + "\n"
        ).encode()
        arm_base = {
            "cases": 180,
            "memory_pressure_cases": 90,
            "recovery_cases": 30,
            "cross_scope_leak_count": 0,
            "failure_codes": {},
            "false_canonical_promotions": 0,
            "unsafe_proposal_rate_under_memory_pressure": 0.0,
            "unsafe_memory_exposure_rate": 0.0,
            "poison_exposure_rate": 0.0,
            "verified_outcome_success_rate": 0.98,
            "canonical_promotion_precision": 1.0,
            "recovery_success_rate": 1.0,
        }
        self.ablation = {
            "schema_version": 3,
            "source_head": "a" * 40,
            "deployment_artifact_sha256": "c" * 64,
            "evaluation_id": "evaluation-1",
            "generated_at": "2026-08-07T00:00:00Z",
            "agent_model": "amazon.nova-micro-v1:0",
            "agent_region": "ap-southeast-2",
            "embedding_model": "amazon.titan-embed-text-v2:0/512",
            "embedding_region": "ap-northeast-2",
            "migration_version": 31,
            "provider": "continuum-synthetic-verifier-v1",
            "retained_for_judge_evidence": True,
            "seed_semantics": "paired isolated episode-state replications",
            "synthetic_non_effecting": True,
            "episode_trace_schema_version": 1,
            "methodology": {
                "case_count_per_arm": 180,
                "metric_contract": [
                    "unsafe_proposal_rate",
                    "unsafe_memory_exposure_rate",
                    "poison_exposure_rate",
                    "verified_outcome_success",
                    "canonical_promotion_precision",
                    "recovery_latency_ms",
                ],
            },
            "arms": {
                "stateless": {**arm_base, "verified_outcome_success_rate": 0.4},
                "raw_rag": {
                    **arm_base,
                    "unsafe_proposal_rate_under_memory_pressure": 0.3,
                    "unsafe_memory_exposure_rate": 0.8,
                    "poison_exposure_rate": 0.8,
                    "verified_outcome_success_rate": 0.7,
                    "canonical_promotion_precision": 0.7,
                    "recovery_success_rate": 0.8,
                    "false_canonical_promotions": 40,
                },
                "continuum": dict(arm_base),
            },
            "continuum_lift_percentage_points": {
                "vs_raw_rag": 28.0,
                "vs_stateless": 58.0,
            },
            "paired_comparisons": {"continuum_vs_raw_rag": {"pairs": 180}},
            "paired_safety_comparisons": {
                "continuum_vs_raw_rag_poison_exposure": {"pairs": 90}
            },
            "variant_counts": {
                "conflict_pressure": 6,
                "explicit_seed": 6,
                "paraphrase": 6,
                "poison_pressure": 6,
                "recovery": 6,
                "stale_pressure": 6,
            },
            "observations": EpisodeDrilldownTests.report()["observations"],
        }
        self.ablation_bytes = (
            json.dumps(self.ablation, sort_keys=True) + "\n"
        ).encode()
        self.ablation_aggregate = build_public_ablation_aggregate(self.ablation)
        self.ablation_aggregate_bytes = (
            json.dumps(self.ablation_aggregate, sort_keys=True) + "\n"
        ).encode()
        self.episode_drilldown = build_public_episode_drilldown(self.ablation)
        self.episode_drilldown_bytes = (
            json.dumps(self.episode_drilldown, sort_keys=True) + "\n"
        ).encode()
        guardian_arms = {
            "raw_rag": {
                "cases": 36,
                "provider_success_rate": 0.86,
                "unsafe_proposals": 5,
                "unsafe_memory_exposures": 23,
                "unsafe_memory_citation_adoptions": 5,
                "false_canonical_promotions": 5,
                "duplicate_effect_count": 0,
                "cleanup_residual_count": 0,
                "cross_scope_leak_count": 0,
            },
            "continuum": {
                "cases": 36,
                "provider_success_rate": 1.0,
                "unsafe_proposals": 0,
                "unsafe_memory_exposures": 0,
                "unsafe_memory_citation_adoptions": 0,
                "false_canonical_promotions": 0,
                "duplicate_effect_count": 0,
                "cleanup_residual_count": 0,
                "cross_scope_leak_count": 0,
            },
        }
        self.release_guardian = {
            "schema_version": 1,
            "generated_at": "2026-08-08T00:00:00Z",
            "source_head": "6" * 40,
            "deployment_artifact_sha256": "5" * 64,
            "evaluation_id": "guardian-evaluation",
            "agent_model": "amazon.nova-micro-v1:0",
            "embedding_model": "amazon.titan-embed-text-v2:0/512",
            "migration_version": 31,
            "repository": "o/r",
            "provider": "github-releases-disposable-sandbox",
            "real_external_provider": True,
            "provider_capability_manifest": {
                "supports_idempotency": True,
                "receipt_lookup": True,
                "reconciliation_timeout_seconds": 30,
            },
            "methodology": {
                "paired_cases": 36,
                "arm_observations": 72,
                "arms": ["raw_rag", "continuum"],
                "provider_state_families": 6,
                "bootstrap_resamples": 10_000,
            },
            "arms": guardian_arms,
            "paired_comparison": {"pairs": 36, "continuum_wins": 5},
            "observations": [
                {
                    "arm": arm,
                    "case_id": f"case-{case_no:02d}",
                    "family": "release-state",
                    "variant": "paired",
                    "outcome_status": "succeeded",
                    "promotion": {"promoted": True},
                }
                for arm in ("raw_rag", "continuum")
                for case_no in range(36)
            ],
            "gate": {"status": "PASS"},
        }
        self.release_guardian_bytes = (
            json.dumps(self.release_guardian, sort_keys=True) + "\n"
        ).encode()
        self.release_guardian_public = build_public_release_guardian(
            self.release_guardian
        )
        self.release_guardian_public_bytes = (
            json.dumps(self.release_guardian_public, sort_keys=True) + "\n"
        ).encode()
        from scripts.build_release_envelope import sha256_bytes

        self.judge = {
            "schema_version": 8,
            "source": {
                "workflow_run_id": 10,
                "workflow_attempt": 1,
                "workflow_url": "https://github.com/o/r/actions/runs/10",
                "deployment_head_sha": "a" * 40,
                "artifact_sha256": "c" * 64,
            },
            "lineage": {
                "baseline_runtime_sha": "1291e2707880700492fe1d7cd431bcba03d68b4c",
                "baseline_documentation_sha": "2a94b4653ab0efe6f2ddeb8701ab05bdbaf403e1",
                "candidate_runtime_sha": "a" * 40,
            },
            "vector_scale": {
                "workflow_run_id": 11,
                "workflow_url": "https://github.com/o/r/actions/runs/11",
                "head_sha": "b" * 40,
                "report_sha256": sha256_bytes(self.scale_bytes),
            },
            "agent_pressure": {
                "workflow_run_id": 14,
                "workflow_url": "https://github.com/o/r/actions/runs/14",
                "head_sha": "f" * 40,
                "report_sha256": sha256_bytes(self.pressure_bytes),
                "workflow_artifact_sha256": "9" * 64,
            },
            "runtime": {
                "migration_version": 31,
                "migration_checksum_drift_absent": True,
                "authorization_mode": "audited-tenant-control-plane",
                "binding_version": 1,
                "binding_event": "bound",
                "health_url": "https://mcp.example.test/healthz",
                "cross_scope_fetch_denied": True,
                "forbidden_memory_visible": False,
                "tenant_control_plane_active": True,
                "control_plane_memory_denied": True,
                "temporary_migration_capability_absent": True,
                "control_plane_and_migrator_role_options_empty": True,
                "database_connections": "bounded-pools-1-4",
            },
            "managed_mcp": {
                "rotation_workflow_run_id": 12,
                "read_tools": ["list_databases", "list_tables"],
                "write_denied_before_secret_access": True,
                "old_provider_key_deleted": True,
                "temporary_github_secret_deleted": True,
            },
            "sandbox_provider": {
                "workflow_run_id": 15,
                "workflow_url": "https://github.com/o/r/actions/runs/15",
                "head_sha": "1291e2707880700492fe1d7cd431bcba03d68b4c",
                "artifact_id": 150,
                "artifact_name": "aws-sandbox-provider-proof-1291e2707880700492fe1d7cd431bcba03d68b4c",
                "artifact_archive_sha256": "8" * 64,
                "report_sha256": sha256_bytes(self.sandbox_bytes),
            },
            "agent_ablation": {
                "workflow_run_id": 10,
                "workflow_url": "https://github.com/o/r/actions/runs/10",
                "head_sha": "a" * 40,
                "artifact_id": 160,
                "artifact_name": "continuum-agent-ablation-" + "a" * 40,
                "artifact_archive_sha256": "7" * 64,
                "report_sha256": sha256_bytes(self.ablation_bytes),
                "public_aggregate_sha256": sha256_bytes(
                    self.ablation_aggregate_bytes
                ),
                "public_aggregate_url": "https://demo.example.test/evidence/ablation.json",
            },
            "episode_drilldown": {
                "schema_version": 1,
                "source_head": "a" * 40,
                "evaluation_id": "evaluation-1",
                "public_url": "https://demo.example.test/evidence/episode-drilldown-v1.json",
                "page_url": "https://demo.example.test/episodes.html",
                "sha256": sha256_bytes(self.episode_drilldown_bytes),
                "paired_episodes": 180,
                "arm_observations": 540,
                "continuum_advantage_episodes": 180,
            },
            "release_guardian": {
                "schema_version": 1,
                "workflow_run_id": 17,
                "workflow_attempt": 1,
                "workflow_url": "https://github.com/o/r/actions/runs/17",
                "workflow_api_url": "https://api.github.com/repos/o/r/actions/runs/17",
                "head_sha": "6" * 40,
                "artifact_id": 170,
                "artifact_name": "continuum-release-guardian-" + "6" * 40,
                "artifact_archive_sha256": "4" * 64,
                "report_sha256": sha256_bytes(self.release_guardian_bytes),
                "public_sha256": sha256_bytes(
                    self.release_guardian_public_bytes
                ),
                "public_url": "https://demo.example.test/evidence/release-guardian-v1.json",
                "page_url": "https://demo.example.test/release-guardian.html",
            },
            "database_policy": {
                "rls_combined_sha256": _migration_receipt(
                    Path(__file__).parents[1],
                    RLS_MIGRATIONS,
                )["combined_sha256"],
            },
            "submission": {
                "id": 1121568,
                "status": "Submitted",
                "project_url": "https://devpost.com/software/x",
                "project_updated_at": "2026-08-02T00:00:00Z",
                "video_url": "https://youtu.be/x",
                "video_duration_seconds": 99.7,
                "video_sha256": "e" * 64,
            },
            "release_envelope": {
                "tag": "hackathon-v1",
                "release_url": "https://github.com/o/r/releases/tag/hackathon-v1",
                "release_api_url": "https://api.github.com/repos/o/r/releases/tags/hackathon-v1",
                "asset_url": "https://github.com/o/r/releases/download/hackathon-v1/continuum-release-envelope-v2.json",
                "asset_name": "continuum-release-envelope-v2.json",
                "sandbox_asset_url": "https://github.com/o/r/releases/download/hackathon-v1/sandbox-provider-proof.json",
                "sandbox_asset_name": "sandbox-provider-proof.json",
                "ablation_asset_url": "https://github.com/o/r/releases/download/hackathon-v1/agent-ablation-v3.json",
                "ablation_asset_name": "agent-ablation-v3.json",
                "drilldown_asset_url": "https://github.com/o/r/releases/download/hackathon-v1/episode-drilldown-v1.json",
                "drilldown_asset_name": "episode-drilldown-v1.json",
                "guardian_asset_url": "https://github.com/o/r/releases/download/hackathon-v1/release-guardian-v1.json",
                "guardian_asset_name": "release-guardian-v1.json",
            },
            "network_sign_once": {
                "schema_version": 2,
                "attestation_api_template": (
                    "https://api.github.com/repos/o/r/attestations/"
                    "sha256:{digest}"
                ),
                "author_bundle_public_url": (
                    "https://demo.example.test/evidence/"
                    "continuum-release-envelope-v2.sigstore.jsonl"
                ),
                "author_bundle_asset_name": (
                    "continuum-release-envelope-v2.sigstore.jsonl"
                ),
                "network_bundle_public_url": (
                    "https://demo.example.test/evidence/"
                    "continuum-release-envelope-v2."
                    "network-attestations.jsonl"
                ),
                "network_bundle_file_name": (
                    "continuum-release-envelope-v2."
                    "network-attestations.jsonl"
                ),
                "subject_name": "continuum-release-envelope-v2.json",
                "author_predicate_type": "https://slsa.dev/provenance/v1",
                "signer_workflow": (
                    "o/r/.github/workflows/release-envelope.yml"
                ),
                "source_ref": "refs/heads/main",
                "runner_environment": "github-hosted",
                "transparency_log": "https://rekor.sigstore.dev",
                "platform_predicate_type": (
                    "https://in-toto.io/attestation/release/v0.2"
                ),
                "platform_signer_identity": (
                    "https://dotcom.releases.github.com"
                ),
                "required_author_attestation_count": 1,
                "required_platform_attestation_count": 1,
                "required_total_attestation_count": 2,
            },
            "release_transaction": {
                "schema_version": 1,
                "coordinator_script": (
                    "scripts/release_transaction_coordinator.py"
                ),
                "receipt_asset_name": "release-transaction-receipt.json",
                "public_receipt_url": (
                    "https://demo.example.test/evidence/"
                    "release-transaction-receipt.json"
                ),
                "states": [
                    "PREPARED",
                    "AUTHOR_ATTESTED",
                    "ASSETS_UPLOADED",
                    "IMMUTABLE",
                    "PAGES_MATERIALIZED",
                ],
                "required_terminal_state": "PAGES_MATERIALIZED",
                "ambiguous_state_fails_closed": True,
            },
            "public_demo": {
                "url": "https://demo.example.test/",
                "verifier_url": "https://demo.example.test/verify.html",
                "evidence_url": "https://demo.example.test/evidence/judge.json",
            },
        }
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()

    def build(
        self,
        blind_holdout_public=None,
        sequential_blind_public=None,
        evidence_story=None,
        ci_recovery_public=None,
        adaptive_diagnosis_public=None,
        transfer_firewall_public=None,
    ):
        blind_bytes = (
            (json.dumps(blind_holdout_public, sort_keys=True) + "\n").encode()
            if blind_holdout_public is not None
            else b""
        )
        sequential_bytes = (
            (json.dumps(sequential_blind_public, sort_keys=True) + "\n").encode()
            if sequential_blind_public is not None
            else b""
        )
        story_bytes = (
            (json.dumps(evidence_story, sort_keys=True) + "\n").encode()
            if evidence_story is not None
            else b""
        )
        ci_recovery_bytes = (
            (json.dumps(ci_recovery_public, sort_keys=True) + "\n").encode()
            if ci_recovery_public is not None
            else b""
        )
        adaptive_diagnosis_bytes = (
            (json.dumps(adaptive_diagnosis_public, sort_keys=True) + "\n").encode()
            if adaptive_diagnosis_public is not None
            else b""
        )
        transfer_firewall_bytes = (
            (json.dumps(transfer_firewall_public, sort_keys=True) + "\n").encode()
            if transfer_firewall_public is not None
            else b""
        )
        return build_envelope(
            self.judge,
            self.scale,
            self.pressure,
            self.sandbox,
            self.ablation,
            self.ablation_aggregate,
            self.episode_drilldown,
            self.release_guardian,
            self.release_guardian_public,
            blind_holdout_public=blind_holdout_public,
            sequential_blind_public=sequential_blind_public,
            evidence_story=evidence_story,
            ci_recovery_public=ci_recovery_public,
            adaptive_diagnosis_public=adaptive_diagnosis_public,
            transfer_firewall_public=transfer_firewall_public,
            judge_bytes=self.judge_bytes,
            scale_bytes=self.scale_bytes,
            pressure_bytes=self.pressure_bytes,
            sandbox_bytes=self.sandbox_bytes,
            ablation_bytes=self.ablation_bytes,
            ablation_aggregate_bytes=self.ablation_aggregate_bytes,
            episode_drilldown_bytes=self.episode_drilldown_bytes,
            release_guardian_bytes=self.release_guardian_bytes,
            release_guardian_public_bytes=self.release_guardian_public_bytes,
            blind_holdout_public_bytes=blind_bytes,
            sequential_blind_public_bytes=sequential_bytes,
            evidence_story_bytes=story_bytes,
            ci_recovery_public_bytes=ci_recovery_bytes,
            adaptive_diagnosis_public_bytes=adaptive_diagnosis_bytes,
            transfer_firewall_public_bytes=transfer_firewall_bytes,
            repo_root=Path(__file__).parents[1],
            repository="o/r",
            commit_sha="d" * 40,
            workflow_run_id=13,
            workflow_url="https://github.com/o/r/actions/runs/13",
            release_tag="hackathon-v1",
            generated_at="2026-08-02T00:00:00+00:00",
        )

    def test_binds_every_release_plane(self) -> None:
        envelope = self.build()
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(envelope["schema_version"], 2)
        self.assertEqual(envelope["application_deployment"]["migration_version"], 31)
        self.assertEqual(envelope["vector_benchmark"]["row_counts"], [10_000, 50_000])
        self.assertEqual(envelope["agent_pressure"]["concurrent_agents"], [10, 25, 50])
        self.assertEqual(len(envelope["database_policy"]["rls"]["files"]), 3)
        self.assertEqual(len(envelope["public_judge_evidence"]["sha256"]), 64)
        self.assertEqual(
            envelope["lineage"]["baseline_runtime_sha"],
            "1291e2707880700492fe1d7cd431bcba03d68b4c",
        )
        self.assertEqual(
            envelope["sandbox_provider"]["report_sha256"],
            self.judge["sandbox_provider"]["report_sha256"],
        )
        self.assertEqual(envelope["agent_ablation"]["arms"]["continuum"]["cases"], 180)
        self.assertEqual(envelope["episode_drilldown"]["population"]["paired_episodes"], 180)
        self.assertEqual(
            envelope["release_guardian"]["methodology"]["paired_cases"],
            36,
        )
        self.assertEqual(
            envelope["network_sign_once"]["required_author_attestation_count"],
            1,
        )
        self.assertEqual(
            envelope["network_sign_once"]["required_total_attestation_count"],
            2,
        )
        self.assertEqual(
            envelope["release_transaction"]["required_terminal_state"],
            "PAGES_MATERIALIZED",
        )

    def test_binds_real_ci_closed_loop_public_projection(self) -> None:
        root = Path(__file__).parents[1]
        ci_recovery = json.loads(
            (root / "public-demo/evidence/ci-recovery-v1.json").read_bytes()
        )
        live_judge = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_bytes()
        )
        self.judge["ci_recovery"] = live_judge["ci_recovery"]
        ci_recovery_bytes = (json.dumps(ci_recovery, sort_keys=True) + "\n").encode()
        self.judge["ci_recovery"]["public_sha256"] = sha256_bytes(
            ci_recovery_bytes
        )
        self.judge["release_envelope"].update(
            {
                "ci_recovery_asset_name": "ci-recovery-v1.json",
                "ci_recovery_asset_url": (
                    "https://github.com/o/r/releases/download/hackathon-v1/"
                    "ci-recovery-v1.json"
                ),
            }
        )
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()
        envelope = self.build(ci_recovery_public=ci_recovery)
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(envelope["ci_recovery"]["workflow_run_id"], 31389008324)
        self.assertEqual(envelope["ci_recovery"]["arms"]["continuum"]["verified_recoveries"], 12)
        self.assertEqual(envelope["ci_recovery"]["arms"]["stateless"]["verified_recoveries"], 12)

        ci_recovery["arms"]["raw_rag"]["verified_recoveries"] = 12
        with self.assertRaisesRegex(RuntimeError, "ci_recovery"):
            self.build(ci_recovery_public=ci_recovery)

    def test_binds_preregistered_adaptive_diagnosis_projection(self) -> None:
        root = Path(__file__).parents[1]
        adaptive = json.loads(
            (root / "public-demo/evidence/adaptive-diagnosis-v1.json").read_bytes()
        )
        live_judge = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_bytes()
        )
        self.judge["adaptive_diagnosis"] = live_judge["adaptive_diagnosis"]
        adaptive_bytes = (json.dumps(adaptive, sort_keys=True) + "\n").encode()
        self.judge["adaptive_diagnosis"]["public_sha256"] = sha256_bytes(
            adaptive_bytes
        )
        self.judge["release_envelope"].update(
            {
                "adaptive_diagnosis_asset_name": "adaptive-diagnosis-v1.json",
                "adaptive_diagnosis_asset_url": (
                    "https://github.com/o/r/releases/download/hackathon-v1/"
                    "adaptive-diagnosis-v1.json"
                ),
            }
        )
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()
        envelope = self.build(adaptive_diagnosis_public=adaptive)
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(
            envelope["adaptive_diagnosis"]["workflow_run_id"], 31400622882
        )
        self.assertEqual(
            envelope["adaptive_diagnosis"]["arms"]["continuum"][
                "recurrence_zero_probe_cases"
            ],
            6,
        )
        self.assertEqual(
            envelope["adaptive_diagnosis"]["paired_comparisons"][
                "continuum_vs_stateless"
            ]["recurrence"]["diagnostic_probe_exact_p_value"],
            0.03125,
        )

        adaptive["arms"]["continuum"]["recurrence_zero_probe_cases"] = 5
        with self.assertRaisesRegex(RuntimeError, "adaptive_diagnosis"):
            self.build(adaptive_diagnosis_public=adaptive)

    def test_binds_counterfactual_transfer_firewall_projection(self) -> None:
        root = Path(__file__).parents[1]
        transfer = json.loads(
            (root / "public-demo/evidence/transfer-firewall-v1.json").read_bytes()
        )
        live_judge = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_bytes()
        )
        self.judge["transfer_firewall"] = live_judge["transfer_firewall"]
        transfer_bytes = (json.dumps(transfer, sort_keys=True) + "\n").encode()
        self.judge["transfer_firewall"]["public_sha256"] = sha256_bytes(
            transfer_bytes
        )
        self.judge["release_envelope"].update(
            {
                "transfer_firewall_asset_name": "transfer-firewall-v1.json",
                "transfer_firewall_asset_url": (
                    "https://github.com/o/r/releases/download/hackathon-v1/"
                    "transfer-firewall-v1.json"
                ),
            }
        )
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()
        envelope = self.build(transfer_firewall_public=transfer)
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(
            envelope["transfer_firewall"]["workflow_run_id"], 31439117749
        )
        self.assertEqual(
            envelope["transfer_firewall"]["arms"]["continuum"][
                "near_neighbor_false_transfers"
            ],
            0,
        )
        self.assertEqual(
            envelope["transfer_firewall"]["arms"]["raw_rag"][
                "near_neighbor_false_transfers"
            ],
            6,
        )

        transfer["arms"]["continuum"]["near_neighbor_false_transfers"] = 1
        with self.assertRaisesRegex(RuntimeError, "counterfactual_transfer"):
            self.build(transfer_firewall_public=transfer)

        transfer = json.loads(
            (root / "public-demo/evidence/transfer-firewall-v1.json").read_bytes()
        )
        transfer["observations"][0]["target_environment_fingerprint"] = (
            transfer["observations"][0]["source_environment_fingerprint"]
        )
        with self.assertRaisesRegex(RuntimeError, "counterfactual_transfer"):
            self.build(transfer_firewall_public=transfer)

    def test_binds_preregistered_blind_holdout(self) -> None:
        blind = json.loads(
            (
                Path(__file__).parents[1]
                / "public-demo/evidence/blind-holdout-v1.json"
            ).read_bytes()
        )
        blind_bytes = (json.dumps(blind, sort_keys=True) + "\n").encode()
        source = blind["source_head"]
        self.judge["blind_holdout"] = {
            "head_sha": source,
            "workflow_run_id": 41,
            "workflow_attempt": 1,
            "workflow_url": "https://github.com/o/r/actions/runs/41",
            "artifact_id": 42,
            "artifact_name": f"continuum-blind-holdout-{source}",
            "artifact_archive_sha256": "e" * 64,
            "report_sha256": "f" * 64,
            "public_sha256": sha256_bytes(blind_bytes),
            "public_url": "https://demo.example.test/evidence/blind.json",
            "commitment_sha256": blind["commitment"]["commitment_sha256"],
            "seal_receipt_sha256": blind["seal_receipt"]["receipt_sha256"],
        }
        self.judge["release_envelope"]["blind_holdout_asset_url"] = (
            "https://github.com/o/r/releases/download/hackathon-v1/"
            "blind-holdout-v1.json"
        )
        envelope = self.build(blind)
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(envelope["blind_holdout"]["public_sha256"], sha256_bytes(blind_bytes))
        self.assertEqual(envelope["blind_holdout"]["methodology"]["paired_cases"], 60)
        self.assertEqual(envelope["blind_holdout"]["arms"]["continuum"]["false_canonical_promotions"], 0)

    def test_v14_binds_sequential_blind_memory_compounding(self) -> None:
        from tests.test_sequential_blind_judge import (
            CANDIDATE_ARCHIVE_SHA,
            CANDIDATE_ARTIFACT_ID,
            CANDIDATE_RUN_ID,
            EVALUATOR_HEAD,
            _public,
        )

        sequential = _public()
        source = sequential["source_head"]
        candidate_name = (
            f"continuum-sequential-blind-{source}-{CANDIDATE_RUN_ID}-1"
        )
        evaluator_name = (
            f"continuum-sequential-blind-evaluator-{CANDIDATE_RUN_ID}-"
            f"{EVALUATOR_HEAD}-51-1"
        )
        sequential["evaluation_replay"] = {
            "schema_version": 1,
            "reason": "github_runner_python_3_10_missing_strenum_before_scoring",
            "candidate_workflow": {
                "run_id": CANDIDATE_RUN_ID,
                "run_attempt": 1,
                "conclusion": "failure",
                "source_head": source,
                "candidate_step_conclusion": "success",
                "cleanup_step_conclusion": "success",
            },
            "candidate_artifact": {
                "id": CANDIDATE_ARTIFACT_ID,
                "name": candidate_name,
                "archive_sha256": CANDIDATE_ARCHIVE_SHA,
            },
            "evaluator_source_head": EVALUATOR_HEAD,
        }
        sequential_bytes = (json.dumps(sequential, sort_keys=True) + "\n").encode()
        self.judge["schema_version"] = 9
        self.judge["sequential_blind_campaign"] = {
            "head_sha": source,
            "evaluator_head_sha": EVALUATOR_HEAD,
            "workflow_run_id": 51,
            "workflow_attempt": 1,
            "workflow_url": "https://github.com/o/r/actions/runs/51",
            "artifact_id": 52,
            "artifact_name": evaluator_name,
            "artifact_archive_sha256": "a" * 64,
            "public_sha256": sha256_bytes(sequential_bytes),
            "public_url": "https://demo.example.test/evidence/sequential.json",
            "page_url": "https://demo.example.test/sequential.html",
            "campaign_id": sequential["campaign_id"],
            "campaign_manifest_sha256": sequential["campaign_manifest"][
                "campaign_manifest_sha256"
            ],
            "campaign_seal_receipt_sha256": sequential[
                "campaign_seal_receipt"
            ]["receipt_sha256"],
            "candidate_workflow_run_id": CANDIDATE_RUN_ID,
            "candidate_workflow_attempt": 1,
            "candidate_workflow_url": (
                f"https://github.com/o/r/actions/runs/{CANDIDATE_RUN_ID}"
            ),
            "candidate_artifact_id": CANDIDATE_ARTIFACT_ID,
            "candidate_artifact_name": candidate_name,
            "candidate_artifact_archive_sha256": CANDIDATE_ARCHIVE_SHA,
        }
        self.judge["release_envelope"]["sequential_blind_asset_name"] = (
            "sequential-blind-v1.json"
        )
        self.judge["release_envelope"]["sequential_blind_asset_url"] = (
            "https://github.com/o/r/releases/download/hackathon-v1/"
            "sequential-blind-v1.json"
        )
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()
        envelope = self.build(sequential_blind_public=sequential)
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(
            envelope["sequential_blind_campaign"]["methodology"][
                "arm_observations"
            ],
            540,
        )
        self.assertEqual(
            envelope["sequential_blind_campaign"]["arms"]["continuum"][
                "false_canonical_promotions"
            ],
            0,
        )
        self.assertEqual(
            envelope["sequential_blind_campaign"]["candidate_artifact_id"],
            CANDIDATE_ARTIFACT_ID,
        )
        self.assertEqual(
            envelope["sequential_blind_campaign"]["evaluation_replay"],
            sequential["evaluation_replay"],
        )
        self.judge["sequential_blind_campaign"]["artifact_name"] = (
            f"continuum-sequential-blind-{source}-51-1"
        )
        self.judge_bytes = (
            json.dumps(self.judge, sort_keys=True) + "\n"
        ).encode()
        with self.assertRaisesRegex(
            RuntimeError, "sequential_blind_artifact_bound"
        ):
            self.build(sequential_blind_public=sequential)

        self.judge["sequential_blind_campaign"]["artifact_name"] = evaluator_name
        self.judge["sequential_blind_campaign"][
            "candidate_artifact_archive_sha256"
        ] = "0" * 64
        self.judge_bytes = (
            json.dumps(self.judge, sort_keys=True) + "\n"
        ).encode()
        with self.assertRaisesRegex(
            RuntimeError, "sequential_blind_artifact_bound"
        ):
            self.build(sequential_blind_public=sequential)

    def test_v15_binds_receipt_compiled_story_and_video(self) -> None:
        from continuum.evidence_story import build_evidence_story

        sequential_path = (
            Path(__file__).parents[1]
            / "public-demo/evidence/sequential-blind-v1.json"
        )
        sequential = json.loads(sequential_path.read_bytes())
        sequential_bytes = (json.dumps(sequential, sort_keys=True) + "\n").encode()
        live_judge = json.loads(
            (
                Path(__file__).parents[1]
                / "public-demo/evidence/judge-verification.json"
            ).read_text(encoding="utf-8")
        )
        reference = live_judge["sequential_blind_campaign"]
        reference["public_sha256"] = sha256_bytes(sequential_bytes)
        self.judge["schema_version"] = 9
        self.judge["sequential_blind_campaign"] = reference
        self.judge["release_envelope"].update(
            {
                "sequential_blind_asset_name": "sequential-blind-v1.json",
                "sequential_blind_asset_url": (
                    "https://github.com/o/r/releases/download/hackathon-v1/"
                    "sequential-blind-v1.json"
                ),
            }
        )
        source_target = "1" * 40
        source_envelope = "2" * 64
        receipt = {
            "release_tag": "hackathon-v1",
            "source_digest": source_target,
            "envelope_sha256": source_envelope,
            "events": [
                {
                    "state": "PAGES_MATERIALIZED",
                    "evidence": {
                        "status": "success",
                        "release_target": source_target,
                        "coordinator_workflow_run_id": 81,
                        "coordinator_artifact_digest": "sha256:" + "3" * 64,
                        "pages_workflow_run_id": 82,
                        "public_receipt_url": "https://demo.example.test/evidence/release-transaction-receipt.json",
                    },
                }
            ],
        }
        story = build_evidence_story(
            self.judge,
            sequential,
            receipt,
            sequential_bytes=sequential_bytes,
            source_release_tag="hackathon-v1",
            source_release_target=source_target,
            source_release_envelope_sha256=source_envelope,
            source_release_sequential_sha256=sha256_bytes(sequential_bytes),
            compiled_at="2026-08-09T00:00:00Z",
        )
        story_bytes = (json.dumps(story, sort_keys=True) + "\n").encode()
        self.judge["schema_version"] = 10
        self.judge["submission"]["video_subtitles_sha256"] = "4" * 64
        self.judge["evidence_story"] = {
            "public_sha256": sha256_bytes(story_bytes),
            "public_url": "https://demo.example.test/evidence/evidence-story-v1.json",
            "page_url": "https://demo.example.test/evidence-story.html",
            "source_release_tag": "hackathon-v1",
            "source_release_target": source_target,
            "source_release_envelope_sha256": source_envelope,
            "source_sequential_sha256": sha256_bytes(sequential_bytes),
            "story_receipt_sha256": story["receipt_sha256"],
            "video_url": self.judge["submission"]["video_url"],
            "video_duration_seconds": self.judge["submission"]["video_duration_seconds"],
            "video_sha256": self.judge["submission"]["video_sha256"],
            "subtitles_sha256": self.judge["submission"]["video_subtitles_sha256"],
        }
        self.judge["release_envelope"].update(
            {
                "evidence_story_asset_name": "evidence-story-v1.json",
                "evidence_story_asset_url": (
                    "https://github.com/o/r/releases/download/hackathon-v1/"
                    "evidence-story-v1.json"
                ),
            }
        )
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()
        envelope = self.build(
            sequential_blind_public=sequential,
            evidence_story=story,
        )
        self.assertEqual(envelope["gates"]["status"], "PASS")
        self.assertEqual(envelope["evidence_story"]["receipt_sha256"], story["receipt_sha256"])
        self.assertEqual(envelope["evidence_story"]["video"]["sha256"], "e" * 64)
        self.assertEqual(envelope["evidence_story"]["claim_boundary"]["continuum_vs_stateless"], "directional_not_confirmatory")

    def test_scale_checksum_and_leakage_fail_closed(self) -> None:
        self.judge["vector_scale"]["report_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.build()
        self.judge["vector_scale"]["report_sha256"] = __import__(
            "hashlib"
        ).sha256(self.scale_bytes).hexdigest()
        self.scale["scales"][1]["beams"][0]["cross_scope_leaked_rows"] = 1
        with self.assertRaisesRegex(RuntimeError, "leakage"):
            self.build()

    def test_stale_scope_or_release_reference_fails_closed(self) -> None:
        self.judge["runtime"]["temporary_migration_capability_absent"] = False
        with self.assertRaisesRegex(RuntimeError, "scope_enforcement"):
            self.build()
        self.judge["runtime"]["temporary_migration_capability_absent"] = True
        self.judge["release_envelope"]["tag"] = "mutable-tag"
        with self.assertRaisesRegex(RuntimeError, "release_reference"):
            self.build()

    def test_pressure_checksum_and_gate_fail_closed(self) -> None:
        self.judge["agent_pressure"]["report_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "pressure_checksum"):
            self.build()
        self.judge["agent_pressure"]["report_sha256"] = __import__(
            "hashlib"
        ).sha256(self.pressure_bytes).hexdigest()
        self.pressure["gate"]["pool_recovery_passed"] = False
        with self.assertRaisesRegex(RuntimeError, "pressure_gate"):
            self.build()

    def test_ablation_projection_and_differentiator_fail_closed(self) -> None:
        self.ablation_aggregate["arms"]["continuum"]["cases"] = 179
        with self.assertRaisesRegex(RuntimeError, "aggregate"):
            self.build()
        self.ablation_aggregate = build_public_ablation_aggregate(self.ablation)
        self.ablation_aggregate_bytes = (
            json.dumps(self.ablation_aggregate, sort_keys=True) + "\n"
        ).encode()
        from scripts.build_release_envelope import sha256_bytes

        self.judge["agent_ablation"]["public_aggregate_sha256"] = sha256_bytes(
            self.ablation_aggregate_bytes
        )
        self.ablation["arms"]["raw_rag"][
            "unsafe_proposal_rate_under_memory_pressure"
        ] = 0.0
        with self.assertRaisesRegex(RuntimeError, "differentiates"):
            self.build()

    def test_optional_ablation_metric_fails_closed_without_type_error(self) -> None:
        self.ablation["arms"]["raw_rag"]["canonical_promotion_precision"] = None
        self.ablation_aggregate = build_public_ablation_aggregate(self.ablation)
        self.ablation_aggregate_bytes = (
            json.dumps(self.ablation_aggregate, sort_keys=True) + "\n"
        ).encode()
        from scripts.build_release_envelope import sha256_bytes

        self.judge["agent_ablation"]["public_aggregate_sha256"] = sha256_bytes(
            self.ablation_aggregate_bytes
        )
        with self.assertRaisesRegex(RuntimeError, "differentiates"):
            self.build()


if __name__ == "__main__":
    unittest.main()

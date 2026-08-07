from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.build_release_envelope import (
    RLS_MIGRATIONS,
    _migration_receipt,
    build_envelope,
    build_public_ablation_aggregate,
    repository_text_bytes,
)


class ReleaseEnvelopeTests(unittest.TestCase):
    def test_repository_text_digest_is_checkout_line_ending_stable(self) -> None:
        self.assertEqual(repository_text_bytes(b"one\r\ntwo\r\n"), b"one\ntwo\n")

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
            "observations": [{} for _ in range(540)],
        }
        self.ablation_bytes = (
            json.dumps(self.ablation, sort_keys=True) + "\n"
        ).encode()
        self.ablation_aggregate = build_public_ablation_aggregate(self.ablation)
        self.ablation_aggregate_bytes = (
            json.dumps(self.ablation_aggregate, sort_keys=True) + "\n"
        ).encode()
        from scripts.build_release_envelope import sha256_bytes

        self.judge = {
            "schema_version": 5,
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
            },
            "public_demo": {
                "url": "https://demo.example.test/",
                "verifier_url": "https://demo.example.test/verify.html",
                "evidence_url": "https://demo.example.test/evidence/judge.json",
            },
        }
        self.judge_bytes = (json.dumps(self.judge, sort_keys=True) + "\n").encode()

    def build(self):
        return build_envelope(
            self.judge,
            self.scale,
            self.pressure,
            self.sandbox,
            self.ablation,
            self.ablation_aggregate,
            judge_bytes=self.judge_bytes,
            scale_bytes=self.scale_bytes,
            pressure_bytes=self.pressure_bytes,
            sandbox_bytes=self.sandbox_bytes,
            ablation_bytes=self.ablation_bytes,
            ablation_aggregate_bytes=self.ablation_aggregate_bytes,
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

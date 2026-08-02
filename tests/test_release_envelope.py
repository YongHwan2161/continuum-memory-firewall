from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.build_release_envelope import build_envelope, repository_text_bytes


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
        from scripts.build_release_envelope import sha256_bytes

        self.judge = {
            "schema_version": 4,
            "source": {
                "workflow_run_id": 10,
                "workflow_attempt": 1,
                "workflow_url": "https://github.com/o/r/actions/runs/10",
                "deployment_head_sha": "a" * 40,
                "artifact_sha256": "c" * 64,
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
                "migration_version": 17,
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
                "asset_url": "https://github.com/o/r/releases/download/hackathon-v1/continuum-release-envelope-v1.json",
                "asset_name": "continuum-release-envelope-v1.json",
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
            judge_bytes=self.judge_bytes,
            scale_bytes=self.scale_bytes,
            pressure_bytes=self.pressure_bytes,
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
        self.assertEqual(envelope["application_deployment"]["migration_version"], 17)
        self.assertEqual(envelope["vector_benchmark"]["row_counts"], [10_000, 50_000])
        self.assertEqual(envelope["agent_pressure"]["concurrent_agents"], [10, 25, 50])
        self.assertEqual(len(envelope["database_policy"]["rls"]["files"]), 3)
        self.assertEqual(len(envelope["public_judge_evidence"]["sha256"]), 64)

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


if __name__ == "__main__":
    unittest.main()

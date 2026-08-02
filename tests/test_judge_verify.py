import unittest
import hashlib
import json
from pathlib import Path

from scripts.judge_readonly_verify import verify_evidence


class JudgeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "schema_version": 4,
            "source": {
                "workflow_run_id": 7,
                "deployment_head_sha": "abc",
                "workflow_api_url": "https://api.example.test/run/7",
            },
            "evaluation": {
                "query_count": 60,
                "recall": {"3": 0.98},
                "cross_scope_leaked_documents": 0,
                "query_plan": {
                    "index_present": True,
                    "index_visible": True,
                    "prefix_columns_match": True,
                },
            },
            "runtime": {
                "health_url": "https://mcp.example.test/healthz",
                "demo_url": "https://mcp.example.test/demo/run",
                "cross_scope_fetch_denied": True,
                "temporary_migration_capability_absent": True,
                "control_plane_and_migrator_role_options_empty": True,
                "tenant_control_plane_active": True,
                "control_plane_memory_denied": True,
                "database_connections": "bounded-pools-1-4",
            },
            "submission": {"status": "Submitted"},
            "public_demo": {
                "url": "https://demo.example.test/",
                "marker": "Continuum Memory Firewall",
            },
            "vector_scale": {
                "url": "https://demo.example.test/vector-scale.json",
                "workflow_run_id": 8,
                "workflow_api_url": "https://api.example.test/benchmark/8",
                "head_sha": "scale-head",
                "report_sha256": "1" * 64,
            },
            "agent_pressure": {
                "url": "https://demo.example.test/agent-pressure.json",
                "workflow_run_id": 9,
                "workflow_api_url": "https://api.example.test/pressure/9",
                "head_sha": "pressure-head",
                "report_sha256": "2" * 64,
            },
        }

        self.scale_report = {
            "source_head": "scale-head",
            "gate": {"status": "PASS"},
            "scales": [
                {
                    "row_count": row_count,
                    "beams": [
                        {
                            "beam_size": beam_size,
                            "cross_scope_leaked_rows": 0,
                            "query_plan": {
                                "reports_vector_search": True,
                                "reports_full_scan": False,
                            },
                        }
                        for beam_size in (1, 32, 128, 512)
                    ],
                }
                for row_count in (10_000, 50_000)
            ],
        }
        self.pressure_report = {
            "source_head": "pressure-head",
            "gate": {
                "status": "PASS",
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

    def fetch_json(self, url):
        if "demo/run" in url:
            return {
                "live": True,
                "storage": {"decision": "ACCEPTED"},
                "poisoning": {"decision": "UNTRUSTED_SOURCE"},
                "action": {"durable_claim_count": 1},
            }
        if "pressure/9" in url:
            return {"conclusion": "success", "head_sha": "pressure-head"}
        if "agent-pressure" in url:
            return self.pressure_report
        if "benchmark" in url:
            return {"conclusion": "success", "head_sha": "scale-head"}
        if "vector-scale" in url:
            return self.scale_report
        if "run" in url:
            return {"conclusion": "success", "head_sha": "abc"}
        return {
            "ok": True,
            "service": "continuum-memory-firewall",
            "authorization_mode": "audited-tenant-control-plane",
            "database_connections": "bounded-pools-1-4",
        }

    def test_read_only_evidence_gate_passes(self):
        report = verify_evidence(
            self.evidence,
            fetch_json=self.fetch_json,
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "read-only-http-get")

    def test_head_mismatch_fails_closed(self):
        report = verify_evidence(
            self.evidence,
            fetch_json=lambda url: (
                {"conclusion": "success", "head_sha": "different"}
                if "run" in url
                else self.fetch_json(url)
            ),
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["workflow_head_matches"])

    def test_scale_scope_leakage_fails_closed(self):
        self.scale_report["scales"][1]["beams"][0][
            "cross_scope_leaked_rows"
        ] = 1
        report = verify_evidence(
            self.evidence,
            fetch_json=self.fetch_json,
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["benchmark_scope_isolation"])

    def test_public_pressure_report_is_checksum_bound(self):
        root = Path(__file__).parents[1]
        pressure_bytes = (root / "public-demo/evidence/agent-pressure.json").read_bytes()
        evidence = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )
        pressure = json.loads(pressure_bytes)
        self.assertEqual(
            hashlib.sha256(pressure_bytes).hexdigest(),
            evidence["agent_pressure"]["report_sha256"],
        )
        self.assertEqual(
            [item["concurrent_agents"] for item in pressure["levels"]],
            [10, 25, 50],
        )
        self.assertEqual(pressure["gate"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

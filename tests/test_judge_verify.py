import unittest

from scripts.judge_readonly_verify import verify_evidence


class JudgeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "schema_version": 3,
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

    def fetch_json(self, url):
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


if __name__ == "__main__":
    unittest.main()

import unittest

from scripts.judge_readonly_verify import verify_evidence


class JudgeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "source": {
                "workflow_run_id": 7,
                "deployment_head_sha": "abc",
                "workflow_api_url": "https://api.example.test/run/7",
            },
            "evaluation": {
                "query_count": 60,
                "recall": {"3": 0.98},
                "cross_scope_leaked_documents": 0,
            },
            "runtime": {
                "health_url": "https://mcp.example.test/healthz",
                "cross_scope_fetch_denied": True,
                "temporary_migration_capability_absent": True,
            },
            "submission": {"status": "Submitted"},
            "public_demo": {
                "url": "https://demo.example.test/",
                "marker": "Continuum Memory Firewall",
            },
        }

    def test_read_only_evidence_gate_passes(self):
        report = verify_evidence(
            self.evidence,
            fetch_json=lambda url: (
                {"conclusion": "success", "head_sha": "abc"}
                if "run" in url
                else {"ok": True, "service": "continuum-memory-firewall"}
            ),
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
                else {"ok": True, "service": "continuum-memory-firewall"}
            ),
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["workflow_head_matches"])


if __name__ == "__main__":
    unittest.main()

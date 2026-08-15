import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DemoVideoCompliancePageTests(unittest.TestCase):
    def test_live_story_exposes_cockroachdb_receipt_without_raw_identifiers(self):
        home = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        app = (ROOT / "public-demo/app.js").read_text(encoding="utf-8")

        for marker in (
            'id="story-receipt"',
            'id="story-memory-id"',
            'id="story-audit-id"',
            'id="story-embedding"',
            'id="story-rls"',
            'id="story-query"',
            "receipt.storage.memory_id.slice(0, 12)",
            "receipt.retrieval.audit_id.slice(0, 12)",
            "receipt.authority.database_rls_enforced",
            "receipt.retrieval.query",
        ):
            self.assertIn(marker, home + app)

        self.assertIn("Only synthetic prefixes are displayed", home)
        self.assertNotIn("JSON.stringify(receipt)", app)

    def test_live_story_does_not_claim_each_replay_creates_memory(self):
        home = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        self.assertIn("01 · CANONICAL MEMORY", home)
        self.assertIn("already canonical", home)
        self.assertNotIn("01 · STORE", home)


if __name__ == "__main__":
    unittest.main()

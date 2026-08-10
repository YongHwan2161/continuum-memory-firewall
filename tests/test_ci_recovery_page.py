from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class CIRecoveryPageTests(unittest.TestCase):
    def test_page_loads_receipt_bound_metrics_and_exposes_claim_boundary(self) -> None:
        page = (ROOT / "public-demo/ci-recovery.html").read_text(encoding="utf-8")
        home = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        app = (ROOT / "public-demo/app.js").read_text(encoding="utf-8")
        for source in (page, app):
            self.assertIn("ci-recovery-v1.json", source)
        self.assertIn("./ci-recovery.html", home)
        self.assertIn("receipts.length===54", page)
        self.assertIn("uniqueRuns.size===54", page)
        self.assertIn("repository_mutation===false", page)
        self.assertIn("stateless arm is intentionally visible", page)
        self.assertIn("does not prove arbitrary-code repair", page)
        self.assertIn('id="failure-link"', page)
        self.assertNotIn("Continuum recovery</span><strong>12/12", page)


if __name__ == "__main__":
    unittest.main()

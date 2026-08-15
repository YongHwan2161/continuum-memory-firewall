from __future__ import annotations

from pathlib import Path
import unittest

from scripts.build_compliant_demo_v9 import narration_paragraphs


ROOT = Path(__file__).resolve().parents[1]


class CompliantDemoV9Tests(unittest.TestCase):
    def test_narration_has_nine_browser_scenes(self) -> None:
        paragraphs = narration_paragraphs(ROOT / "docs" / "demo" / "DEMO_NARRATION_V9.md")
        self.assertEqual(9, len(paragraphs))
        joined = " ".join(paragraphs)
        for claim in ("real browser action", "CockroachDB", "Titan", "Raw RAG", "One click"):
            self.assertIn(claim, joined)

    def test_capture_uses_real_public_routes_and_live_action(self) -> None:
        source = (ROOT / "scripts" / "capture_compliant_demo_v9.cjs").read_text(encoding="utf-8")
        for route in ("online-memory-lineage.html", "episodes.html", "outcome-replay-cas.html", "verify.html"):
            self.assertIn(route, source)
        self.assertIn('clickVisible(page, "#run-story")', source)
        self.assertIn("live Titan/CockroachDB", source)
        self.assertIn('clickVisible(page, "#run")', source)
        self.assertIn("All read-only gates passed", source)

    def test_caption_overlay_is_burned_into_browser_pixels(self) -> None:
        source = (ROOT / "scripts" / "capture_compliant_demo_v9.cjs").read_text(encoding="utf-8")
        self.assertIn("continuum-demo-caption", source)
        self.assertIn("recordVideo", source)
        self.assertNotIn("page.screenshot", source)


if __name__ == "__main__":
    unittest.main()

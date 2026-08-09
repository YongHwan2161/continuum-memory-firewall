from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.promote_evidence_story_v7 import promote_evidence_story


ROOT = Path(__file__).resolve().parents[1]


class PromoteEvidenceStoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.judge = json.loads((ROOT / "public-demo/evidence/judge-verification.json").read_text(encoding="utf-8"))
        self.judge["schema_version"] = 9
        self.story_bytes = (ROOT / "public-demo/evidence/evidence-story-v1.json").read_bytes()
        self.story = json.loads(self.story_bytes)

    def promote(self, **overrides):
        values = {
            "story_bytes": self.story_bytes,
            "repository": "YongHwan2161/continuum-memory-firewall",
            "release_tag": "hackathon-v15",
            "video_url": "https://youtu.be/QQxfQaDVz9c",
            "video_duration_seconds": 97.02,
            "video_sha256": "3" * 64,
            "subtitles_sha256": "4" * 64,
            "project_version": 20,
            "project_updated_at": "2026-08-09T10:54:00.418-04:00",
        }
        values.update(overrides)
        return promote_evidence_story(self.judge, self.story, **values)

    def test_promotes_video_story_and_release_atomically(self) -> None:
        promoted = self.promote()
        self.assertEqual(promoted["schema_version"], 10)
        self.assertEqual(promoted["submission"]["project_version"], 20)
        self.assertEqual(promoted["submission"]["video_url"], "https://youtu.be/QQxfQaDVz9c")
        self.assertEqual(promoted["release_envelope"]["tag"], "hackathon-v15")
        self.assertTrue(promoted["release_envelope"]["asset_url"].endswith("hackathon-v15/continuum-release-envelope-v2.json"))
        self.assertTrue(promoted["release_envelope"]["evidence_story_asset_url"].endswith("hackathon-v15/evidence-story-v1.json"))
        self.assertEqual(promoted["evidence_story"]["source_release_tag"], "hackathon-v14")
        self.assertEqual(promoted["evidence_story"]["gate"]["status"], "PASS")

    def test_rejects_unbounded_video_and_receipt(self) -> None:
        for overrides, message in (
            ({"video_duration_seconds": 121}, "duration"),
            ({"video_sha256": "bad"}, "video SHA"),
            ({"subtitles_sha256": "bad"}, "subtitles SHA"),
            ({"project_version": 0}, "Devpost"),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(RuntimeError, message):
                    self.promote(**overrides)

    def test_rejects_mutated_story(self) -> None:
        self.story["metrics"]["target_successes"]["continuum"] = 144
        with self.assertRaisesRegex(RuntimeError, "self-check"):
            self.promote()


if __name__ == "__main__":
    unittest.main()

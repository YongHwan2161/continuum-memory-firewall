from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from continuum.provider_origin_story import verify_provider_origin_story
from scripts.judge_readonly_verify import verify_provider_origin_story_delivery


ROOT = Path(__file__).resolve().parents[1]
JUDGE_PATH = ROOT / "public-demo" / "evidence" / "judge-verification.json"
STORY_PATH = ROOT / "public-demo" / "evidence" / "provider-origin-story-v1.json"


class JudgeClosureV31Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.judge = json.loads(JUDGE_PATH.read_text(encoding="utf-8"))
        self.story_bytes = STORY_PATH.read_bytes()
        self.story = json.loads(self.story_bytes)

    def test_current_video_devpost_and_story_are_one_delivery_contract(self) -> None:
        verify_provider_origin_story(self.story)
        reference = self.judge["provider_origin_story"]
        submission = self.judge["submission"]
        normalized_sha = hashlib.sha256(
            self.story_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()

        self.assertEqual(self.judge["schema_version"], 19)
        self.assertEqual(normalized_sha, reference["public_sha256"])
        self.assertEqual(
            self.story["receipt_sha256"], reference["story_receipt_sha256"]
        )
        self.assertEqual(reference["video_url"], submission["video_url"])
        self.assertEqual(reference["video_sha256"], submission["video_sha256"])
        self.assertEqual(reference["devpost"]["project_version"], 26)
        self.assertEqual(reference["devpost"]["submission_id"], submission["id"])
        self.assertEqual(reference["caption_delivery"]["mode"], "burned-in")
        self.assertTrue(reference["caption_delivery"]["publicly_verifiable"])

    def test_readonly_delivery_verifier_accepts_exact_bytes_only(self) -> None:
        fetch = lambda _url: self.story_bytes
        self.assertTrue(
            verify_provider_origin_story_delivery(self.judge, fetch_bytes=fetch)
        )

        mutated = deepcopy(self.judge)
        mutated["submission"]["video_sha256"] = "0" * 64
        self.assertFalse(
            verify_provider_origin_story_delivery(mutated, fetch_bytes=fetch)
        )

    def test_first_screen_is_receipt_derived_and_release_bound(self) -> None:
        page = (ROOT / "public-demo" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "public-demo" / "app.js").read_text(encoding="utf-8")
        release = self.judge["release_envelope"]

        for element_id in (
            "closure-raw-promotions",
            "closure-continuum-promotions",
            "closure-future-success",
            "closure-authority-attacks",
        ):
            self.assertIn(f'id="{element_id}"', page)
        self.assertNotIn(">48<", page)
        self.assertIn("function renderJudgeClosure(sequential, outcomeReplayCas)", script)
        self.assertIn("raw.false_canonical_promotions", script)
        self.assertIn("continuum.target_provider_successes", script)
        self.assertIn("outcomeReplayCas.attestation.negative_codes", script)
        self.assertEqual(release["tag"], "hackathon-v32")
        self.assertEqual(
            release["provider_origin_story_asset_name"],
            "provider-origin-story-v1.json",
        )
        self.assertEqual(
            self.judge["release_transaction"]["required_terminal_state"],
            "BROWSER_VERIFIED",
        )
        self.assertEqual(
            self.judge["browser_verification"]["required_ui_check_count"], 39
        )


if __name__ == "__main__":
    unittest.main()

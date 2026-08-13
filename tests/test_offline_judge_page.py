import json
import unittest
from pathlib import Path

from scripts.offline_judge_capsule import UI_CHECK_SOURCES


class OfflineJudgePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).parents[1]
        cls.html = (root / "public-demo/verify.html").read_text(encoding="utf-8")
        cls.javascript = (root / "public-demo/offline-judge.js").read_text(
            encoding="utf-8"
        )
        cls.judge = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )

    def test_primary_button_uses_only_offline_listener(self) -> None:
        self.assertIn('<script src="./offline-judge.js"></script>', self.html)
        self.assertIn("script-src 'self' 'unsafe-inline'", self.html)
        self.assertNotIn(
            "document.querySelector('#run').addEventListener('click',run);",
            self.html,
        )
        self.assertIn("button.addEventListener('click', runOffline)", self.javascript)

    def test_offline_script_has_no_github_api_endpoint_or_token(self) -> None:
        self.assertNotIn("api.github.com", self.javascript)
        self.assertNotIn("Authorization", self.javascript)
        self.assertIn("credentials: 'omit'", self.javascript)
        self.assertIn("github_api_requests: 0", self.javascript)

    def test_schema_seventeen_advertises_release_bound_capsule(self) -> None:
        self.assertEqual(self.judge["schema_version"], 17)
        reference = self.judge["offline_judge_capsule"]
        self.assertEqual(reference["schema_version"], 1)
        self.assertEqual(reference["github_api_requests_per_judge_click"], 0)
        self.assertEqual(
            self.judge["release_envelope"]["offline_judge_capsule_asset_name"],
            reference["asset_name"],
        )
        self.assertEqual(len(UI_CHECK_SOURCES), 37)
        self.assertIn("values.providerOriginStory = providerStoryBound", self.javascript)
        self.assertIn("effective_check_count", self.javascript)
        self.assertIn("same_origin_static_gets: 7", self.javascript)


if __name__ == "__main__":
    unittest.main()

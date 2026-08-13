import json
import subprocess
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
        cls.javascript_path = root / "public-demo/offline-judge.js"
        cls.provider_story_path = (
            root / "public-demo/evidence/provider-origin-story-v1.json"
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
        self.assertIn("JSON.stringify(canonical(body)) + '\\n'", self.javascript)
        self.assertIn("providerStoryReceiptHash(providerStory)", self.javascript)
        self.assertIn("effective_check_count", self.javascript)
        self.assertIn("same_origin_static_gets: 7", self.javascript)

    def test_production_browser_hash_matches_provider_story_receipt(self) -> None:
        story = json.loads(self.provider_story_path.read_text(encoding="utf-8"))
        node_script = f"""
const fs = require('fs');
global.window = globalThis;
global.document = {{querySelector() {{ return {{addEventListener() {{}}}}; }}}};
global.canonical = value => Array.isArray(value)
  ? value.map(global.canonical)
  : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, global.canonical(value[key])]))
    : value;
global.sha256Hex = async buffer => {{
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('');
}};
eval(fs.readFileSync({json.dumps(str(self.javascript_path))}, 'utf8'));
const story = JSON.parse(fs.readFileSync({json.dumps(str(self.provider_story_path))}, 'utf8'));
window.__continuumOfflineVerificationInternals.providerStoryReceiptHash(story)
  .then(value => process.stdout.write(value));
"""
        result = subprocess.run(
            ["node", "-e", node_script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout, story["receipt_sha256"])


if __name__ == "__main__":
    unittest.main()

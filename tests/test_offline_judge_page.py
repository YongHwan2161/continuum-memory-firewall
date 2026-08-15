import base64
import hashlib
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
        cls.judge = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )
        cls.browser_reference = cls.judge["browser_verification"]
        cls.javascript_path = root / "public-demo" / cls.browser_reference[
            "script_asset_name"
        ]
        cls.javascript_bytes = cls.javascript_path.read_bytes()
        cls.javascript = cls.javascript_bytes.decode("utf-8")
        cls.provider_story_path = (
            root / "public-demo/evidence/provider-origin-story-v1.json"
        )

    def test_primary_button_uses_only_offline_listener(self) -> None:
        expected = (
            '<script id="continuum-offline-judge-script" '
            f'src="./{self.browser_reference["script_asset_name"]}" '
            f'integrity="{self.browser_reference["script_integrity"]}" '
            'crossorigin="anonymous"></script>'
        )
        self.assertIn(expected, self.html)
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

    def test_schema_nineteen_advertises_release_bound_browser_gate(self) -> None:
        self.assertEqual(self.judge["schema_version"], 19)
        reference = self.judge["offline_judge_capsule"]
        self.assertEqual(reference["schema_version"], 1)
        self.assertEqual(reference["github_api_requests_per_judge_click"], 0)
        self.assertEqual(
            self.judge["release_envelope"]["offline_judge_capsule_asset_name"],
            reference["asset_name"],
        )
        self.assertEqual(len(UI_CHECK_SOURCES), 37)
        self.assertIn("values.providerOriginStory = providerStoryBound", self.javascript)
        self.assertIn("values.kmsAuthority = kmsAuthorityBound", self.javascript)
        self.assertIn("failed_epoch_promoted_to_pass === false", self.javascript)
        self.assertIn("same(capsuleReference.relay, relayEvidence)", self.javascript)
        self.assertIn("kms-authority-lifecycle-v1.json", self.javascript)
        self.assertIn("JSON.stringify(canonical(body)) + '\\n'", self.javascript)
        self.assertIn("providerStoryReceiptHash(providerStory)", self.javascript)
        self.assertIn("effective_check_count", self.javascript)
        self.assertIn("same_origin_static_gets: 8", self.javascript)
        digest = hashlib.sha256(self.javascript_bytes).hexdigest()
        integrity = "sha256-" + base64.b64encode(
            hashlib.sha256(self.javascript_bytes).digest()
        ).decode("ascii")
        self.assertEqual(self.browser_reference["script_sha256"], digest)
        self.assertEqual(
            self.browser_reference["script_asset_name"],
            f"assets/offline-judge.{digest}.js",
        )
        self.assertEqual(self.browser_reference["script_integrity"], integrity)
        self.assertEqual(
            self.browser_reference["required_terminal_state"],
            "BROWSER_VERIFIED",
        )
        self.assertIn("CANDIDATE_PASS", self.javascript)
        relay = reference["relay"]
        self.assertTrue(relay["enabled"])
        self.assertTrue(relay["source_release_immutable"])
        self.assertEqual(relay["failed_pages_conclusion"], "failure")
        self.assertEqual(relay["failed_pages_workflow_run_id"], 31861327695)
        self.assertEqual(relay["source_release_tag"], "hackathon-v34")
        self.assertEqual(relay["source_predecessor_release_tag"], "hackathon-v32")
        self.assertEqual(
            relay["source_asset_sha256"],
            "e29019a862b0957f0e1db3d11c9a411ec0498aea6c1e5501fa628ffde494d47a",
        )

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

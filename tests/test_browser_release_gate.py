import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.release_transaction_coordinator import advance_receipt
from tests.test_release_transaction_coordinator import (
    ReleaseTransactionCoordinatorTests,
)


ROOT = Path(__file__).resolve().parents[1]


class BrowserReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.judge = json.loads(
            (ROOT / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )
        self.reference = self.judge["browser_verification"]
        self.asset = ROOT / "public-demo" / self.reference["script_asset_name"]
        self.workflow = (ROOT / ".github/workflows/pages.yml").read_text(
            encoding="utf-8"
        )

    def test_runtime_asset_is_content_addressed_and_sri_bound(self) -> None:
        payload = self.asset.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        integrity = "sha256-" + base64.b64encode(
            hashlib.sha256(payload).digest()
        ).decode("ascii")
        self.assertEqual(self.reference["script_sha256"], digest)
        self.assertEqual(
            self.reference["script_asset_name"],
            f"assets/offline-judge.{digest}.js",
        )
        self.assertEqual(self.reference["script_integrity"], integrity)
        self.assertFalse((ROOT / "public-demo/offline-judge.js").exists())
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("public-demo/assets/offline-judge.*.js binary", attributes)

    def test_pages_workflow_has_candidate_and_final_browser_gates(self) -> None:
        self.assertEqual(self.workflow.count("uses: actions/deploy-pages@"), 2)
        for marker in (
            "github-pages-candidate",
            "browser-verification-candidate-${{ github.run_id }}",
            "--phase candidate",
            "--to-state BROWSER_VERIFIED",
            "--expected-state BROWSER_VERIFIED",
            "github-pages-browser-verified",
            "--phase final",
            "browser-verification-final-${{ github.run_id }}",
            "verification.github_api_requests == 0",
            "verification.console_error_count == 0",
        ):
            self.assertIn(marker, self.workflow)
        self.assertIn("actions/setup-node@2028fbc5", self.workflow)
        self.assertIn("playwright install --with-deps chromium", self.workflow)
        self.assertEqual(
            self.workflow.count(".verification.ui_check_count == 39"), 2
        )
        self.assertIn("for attempt in $(seq 1 12)", self.workflow)
        self.assertIn('test "$final_ok" = true', self.workflow)
        browser_script = (
            ROOT / "scripts/browser_release_verify.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn("pageResult.rows.total !== 39", browser_script)
        self.assertIn("state.same_origin_static_gets !== 8", browser_script)

    def test_browser_runtime_dependency_is_exact_and_audit_fixed(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(package["devDependencies"]["playwright"], "1.62.1")
        self.assertEqual(
            lock["packages"]["node_modules/playwright"]["version"], "1.62.1"
        )

    def test_browser_receipt_rejects_any_relaxed_gate(self) -> None:
        fixture = ReleaseTransactionCoordinatorTests()
        fixture.setUp()
        pages = fixture._pages()
        valid = fixture._browser()["events"][-1]["evidence"]
        mutations = (
            ("browser_context_fresh", False),
            ("github_api_requests", 1),
            ("console_error_count", 1),
            ("ui_check_count", 37),
            ("script_sha256", "0" * 64),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                evidence = deepcopy(valid)
                evidence[key] = value
                if key == "script_sha256":
                    evidence["script_asset_name"] = f"assets/offline-judge.{value}.js"
                with self.assertRaises(RuntimeError):
                    advance_receipt(
                        pages,
                        to_state="BROWSER_VERIFIED",
                        evidence=evidence,
                        observed_at="2026-08-08T00:05:00Z",
                    )


if __name__ == "__main__":
    unittest.main()

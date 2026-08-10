import json
from pathlib import Path
import unittest

from scripts.promote_transfer_firewall_evidence import build_reference


class PromoteTransferFirewallEvidenceTests(unittest.TestCase):
    def test_live_projection_builds_exact_receipt_reference(self) -> None:
        root = Path(__file__).parents[1]
        public_path = root / "public-demo/evidence/transfer-firewall-v1.json"
        raw_path = (
            root
            / "build/evidence/transfer-firewall-run-31439117749/"
            "transfer-firewall-private.json"
        )
        if not public_path.exists() or not raw_path.exists():
            self.skipTest("private live artifact is intentionally not committed")
        public_bytes = public_path.read_bytes()
        reference = build_reference(
            json.loads(raw_path.read_bytes()),
            json.loads(public_bytes),
            public_bytes=public_bytes,
            artifact_id=9082282513,
            artifact_name=(
                "continuum-transfer-firewall-"
                "361c3ec8ed6ee1a7c09ae30bcf80d9d22aa44fc9-31439117749-1"
            ),
            artifact_archive_sha256=(
                "1c103f9e454e6886ebf09f23b494f44d2755696aa1d6b5ca7b779125118add71"
            ),
            page_url="https://demo.test/transfer-firewall.html",
            public_url="https://demo.test/evidence/transfer-firewall-v1.json",
        )
        self.assertEqual(reference["workflow_run_id"], 31439117749)
        self.assertEqual(reference["child_workflow_runs"], 84)
        self.assertEqual(reference["counterfactual_pairs"], 6)
        self.assertEqual(reference["target_cases"], 12)


if __name__ == "__main__":
    unittest.main()

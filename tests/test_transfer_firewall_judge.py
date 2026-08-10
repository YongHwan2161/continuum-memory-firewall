import json
from pathlib import Path
import unittest

from scripts.judge_readonly_verify import verify_transfer_firewall


ROOT = Path(__file__).parents[1]


class TransferFirewallJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        judge = json.loads(
            (ROOT / "public-demo/evidence/judge-verification.json").read_bytes()
        )
        self.reference = judge["transfer_firewall"]
        self.public_bytes = (
            ROOT / "public-demo/evidence/transfer-firewall-v1.json"
        ).read_bytes()

    def _fetch(self, url: str) -> dict:
        if url == self.reference["workflow_api_url"]:
            return {
                "id": self.reference["workflow_run_id"],
                "run_attempt": self.reference["workflow_attempt"],
                "conclusion": "success",
                "head_sha": self.reference["head_sha"],
            }
        if url == self.reference["artifact_api_url"]:
            return {
                "id": self.reference["artifact_id"],
                "name": self.reference["artifact_name"],
                "digest": "sha256:" + self.reference["artifact_archive_sha256"],
                "expired": False,
                "workflow_run": {"id": self.reference["workflow_run_id"]},
            }
        raise AssertionError(url)

    def test_exact_parent_seal_and_all_child_receipts_pass(self) -> None:
        self.assertTrue(
            verify_transfer_firewall(
                {"transfer_firewall": self.reference},
                fetch_json=self._fetch,
                fetch_bytes=lambda _url: self.public_bytes,
            )
        )

    def test_near_neighbor_or_receipt_tampering_fails_closed(self) -> None:
        report = json.loads(self.public_bytes)
        report["arms"]["continuum"]["near_neighbor_false_transfers"] = 1
        tampered = (json.dumps(report, sort_keys=True) + "\n").encode()
        self.assertFalse(
            verify_transfer_firewall(
                {"transfer_firewall": self.reference},
                fetch_json=self._fetch,
                fetch_bytes=lambda _url: tampered,
            )
        )


if __name__ == "__main__":
    unittest.main()

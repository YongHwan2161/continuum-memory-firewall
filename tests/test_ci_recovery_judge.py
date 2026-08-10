import json
from pathlib import Path
import unittest

from scripts.judge_readonly_verify import verify_ci_recovery


ROOT = Path(__file__).parents[1]


class CIRecoveryJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        judge = json.loads(
            (ROOT / "public-demo/evidence/judge-verification.json").read_bytes()
        )
        self.reference = judge["ci_recovery"]
        self.public_bytes = (
            ROOT / "public-demo/evidence/ci-recovery-v1.json"
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

    def test_exact_parent_artifact_and_all_child_receipts_pass(self) -> None:
        passed = verify_ci_recovery(
            {"ci_recovery": self.reference},
            fetch_json=self._fetch,
            fetch_bytes=lambda _url: self.public_bytes,
        )
        self.assertTrue(passed)

    def test_public_result_tampering_fails_closed(self) -> None:
        report = json.loads(self.public_bytes)
        report["arms"]["raw_rag"]["verified_recoveries"] = 12
        tampered = (json.dumps(report, sort_keys=True) + "\n").encode()
        passed = verify_ci_recovery(
            {"ci_recovery": self.reference},
            fetch_json=self._fetch,
            fetch_bytes=lambda _url: tampered,
        )
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()

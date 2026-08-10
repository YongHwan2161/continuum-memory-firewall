import json
from pathlib import Path
import unittest

from scripts.promote_ci_recovery_evidence import build_reference


class PromoteCIRecoveryEvidenceTests(unittest.TestCase):
    def test_live_projection_builds_exact_receipt_reference(self) -> None:
        root = Path(__file__).parents[1]
        public_path = root / "public-demo/evidence/ci-recovery-v1.json"
        if not public_path.exists():
            self.skipTest("live public projection has not been promoted")
        public_bytes = public_path.read_bytes()
        public = json.loads(public_bytes)
        raw_path = root / "build/live-ci-recovery-31389008324/ci-recovery-private.json"
        if not raw_path.exists():
            self.skipTest("private workflow artifact is intentionally not committed")
        raw = json.loads(raw_path.read_bytes())
        reference = build_reference(
            raw,
            public,
            public_bytes=public_bytes,
            artifact_id=9062964949,
            artifact_name=(
                "continuum-ci-recovery-"
                "3a77fa7575d6b324ae367995bd398fbd0b758ca1-31389008324-1"
            ),
            artifact_archive_sha256=(
                "08d5d0d0cc7b3719fcdea306221924d2db6687580c42e3b980fccdcb3a8a274f"
            ),
            page_url="https://demo.test/ci-recovery.html",
            public_url="https://demo.test/evidence/ci-recovery-v1.json",
        )
        self.assertEqual(reference["workflow_run_id"], 31389008324)
        self.assertEqual(reference["child_workflow_runs"], 54)
        self.assertEqual(reference["public_sha256"], "8d0f6ac85c22f052f2f3968deeb3f86c311164773d06def3e9f87977cb4e9236")


if __name__ == "__main__":
    unittest.main()

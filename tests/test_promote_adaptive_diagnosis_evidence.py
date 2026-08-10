import json
from pathlib import Path
import unittest

from scripts.promote_adaptive_diagnosis_evidence import build_reference


class PromoteAdaptiveDiagnosisEvidenceTests(unittest.TestCase):
    def test_live_projection_builds_exact_receipt_reference(self) -> None:
        root = Path(__file__).parents[1]
        public_path = root / "public-demo/evidence/adaptive-diagnosis-v1.json"
        raw_path = (
            root
            / "build/live-adaptive-31400622882/adaptive-diagnosis-private.json"
        )
        if not public_path.exists() or not raw_path.exists():
            self.skipTest("private live artifact is intentionally not committed")
        public_bytes = public_path.read_bytes()
        reference = build_reference(
            json.loads(raw_path.read_bytes()),
            json.loads(public_bytes),
            public_bytes=public_bytes,
            artifact_id=9067731798,
            artifact_name=(
                "continuum-adaptive-diagnosis-"
                "a8274319e548c91a6eb2910ca8345011aa6f2c3e-31400622882-1"
            ),
            artifact_archive_sha256=(
                "7164eb8e07a0ebe600004c80b848ebe32fedfabda12f14ccbdbac978a45b7485"
            ),
            page_url="https://demo.test/adaptive-diagnosis.html",
            public_url="https://demo.test/evidence/adaptive-diagnosis-v1.json",
        )
        self.assertEqual(reference["workflow_run_id"], 31400622882)
        self.assertEqual(reference["child_workflow_runs"], 84)
        self.assertEqual(reference["paired_cases"], 12)


if __name__ == "__main__":
    unittest.main()

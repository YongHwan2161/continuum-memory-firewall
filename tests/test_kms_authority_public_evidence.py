from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from continuum.kms_authority_proof import validate_kms_authority_proof
from scripts.judge_readonly_verify import verify_kms_outcome_authority
from scripts.promote_kms_authority_evidence import build_reference


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PATH = ROOT / "public-demo/evidence/kms-authority-lifecycle-v1.json"
JUDGE_PATH = ROOT / "public-demo/evidence/judge-verification.json"


class KmsAuthorityPublicEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.public_bytes = PUBLIC_PATH.read_bytes()
        self.report = json.loads(self.public_bytes)
        self.judge = json.loads(JUDGE_PATH.read_text(encoding="utf-8"))
        self.reference = self.judge["kms_outcome_authority"]

    def test_live_receipt_is_exact_run_artifact_and_release_bound(self) -> None:
        validate_kms_authority_proof(self.report)
        digest = hashlib.sha256(
            self.public_bytes.replace(b"\r\n", b"\n")
        ).hexdigest()
        self.assertEqual(
            digest,
            "9492eb130053e2b496e58695eeb9c110f423934be18888cbe320f810dda353d2",
        )
        self.assertEqual(digest, self.reference["public_sha256"])
        self.assertEqual(self.reference["workflow_run_id"], 31813682371)
        self.assertEqual(self.reference["artifact_id"], 9224227375)
        self.assertEqual(
            self.reference["artifact_archive_sha256"],
            "66f3a5e4a8a9e39f40f4f8b70845e2a086b54078ed6f6404e7b92a3d0727b9d4",
        )
        self.assertEqual(self.reference["gate_check_count"], 18)
        self.assertEqual(self.reference["authority_epochs"], [1, 2, 3])
        self.assertTrue(self.reference["action_worker_kms_sign_denied"])
        self.assertEqual(self.reference["private_handoff_objects_remaining"], 0)
        release = self.judge["release_envelope"]
        self.assertEqual(release["tag"], "hackathon-v35")
        self.assertEqual(
            release["kms_outcome_authority_asset_name"],
            "kms-authority-lifecycle-v1.json",
        )

    def test_reference_builder_reproduces_public_identity(self) -> None:
        rebuilt = build_reference(
            self.report,
            public_bytes=self.public_bytes,
            repository="YongHwan2161/continuum-memory-firewall",
            artifact_id=self.reference["artifact_id"],
            artifact_name=self.reference["artifact_name"],
            artifact_archive_sha256=self.reference[
                "artifact_archive_sha256"
            ],
            page_url=self.reference["page_url"],
            public_url=self.reference["public_url"],
        )
        self.assertEqual(rebuilt, self.reference)

    def test_readonly_verifier_rejects_lineage_drift(self) -> None:
        workflow = {
            "id": self.reference["workflow_run_id"],
            "run_attempt": self.reference["workflow_attempt"],
            "head_sha": self.reference["head_sha"],
            "conclusion": "success",
        }
        artifact = {
            "id": self.reference["artifact_id"],
            "name": self.reference["artifact_name"],
            "digest": "sha256:" + self.reference["artifact_archive_sha256"],
            "expired": False,
            "workflow_run": {"id": self.reference["workflow_run_id"]},
        }

        def fetch_json(url: str) -> dict:
            if url == self.reference["workflow_api_url"]:
                return workflow
            if url == self.reference["artifact_api_url"]:
                return artifact
            raise AssertionError(url)

        self.assertTrue(
            verify_kms_outcome_authority(
                self.judge,
                fetch_json=fetch_json,
                fetch_bytes=lambda _url: self.public_bytes,
            )
        )
        mutated = deepcopy(self.judge)
        mutated["kms_outcome_authority"]["workflow_run_id"] += 1
        self.assertFalse(
            verify_kms_outcome_authority(
                mutated,
                fetch_json=fetch_json,
                fetch_bytes=lambda _url: self.public_bytes,
            )
        )

    def test_public_surfaces_and_release_workflow_require_the_receipt(self) -> None:
        page = (ROOT / "public-demo/kms-authority.html").read_text(
            encoding="utf-8"
        )
        index = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        verifier = (ROOT / "public-demo/verify.html").read_text(
            encoding="utf-8"
        )
        workflow = (ROOT / ".github/workflows/release-envelope.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("The action worker can execute", page)
        self.assertIn("kms_outcome_authority_artifact_bound", page)
        self.assertIn("./kms-authority.html", index)
        self.assertIn("kmsAuthority:", verifier)
        self.assertIn("kmsAuthorityArtifact", verifier)
        self.assertIn("kms-authority-lifecycle-v1.json.sha256", workflow)
        self.assertIn("validate_kms_authority_proof(kms_authority)", workflow)


if __name__ == "__main__":
    unittest.main()

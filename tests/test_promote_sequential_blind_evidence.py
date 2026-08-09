import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from continuum.blind_holdout import canonical_json_bytes
from scripts.promote_sequential_blind_evidence import promote
from tests.test_sequential_blind_judge import (
    ARCHIVE_SHA,
    ARTIFACT_ID,
    ARTIFACT_NAME,
    RUN_ID,
    _public,
)


class PromoteSequentialBlindEvidenceTests(unittest.TestCase):
    def test_promotes_exact_provider_receipts_and_v14_urls(self) -> None:
        public = _public()
        source = public["source_head"]
        workflow = {
            "id": RUN_ID,
            "run_attempt": 1,
            "conclusion": "success",
            "head_sha": source,
        }
        artifact = {
            "id": ARTIFACT_ID,
            "name": ARTIFACT_NAME,
            "digest": "sha256:" + ARCHIVE_SHA,
            "expired": False,
            "workflow_run": {"id": RUN_ID},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            judge_path = root / "judge.json"
            campaign_path = root / "campaign.json"
            output_path = root / "sequential.json"
            workflow_path = root / "workflow.json"
            artifact_path = root / "artifact.json"
            judge_path.write_text(
                json.dumps(
                    {
                        "schema_version": 8,
                        "claim_boundary": "old",
                        "public_demo": {"url": "https://demo.example.test/"},
                        "release_envelope": {
                            "tag": "hackathon-v13",
                            "release_url": "old",
                            "release_api_url": "old",
                            "asset_name": "continuum-release-envelope-v2.json",
                            "asset_url": "old",
                            "blind_holdout_asset_name": "blind-holdout-v1.json",
                            "blind_holdout_asset_url": "old",
                        },
                    }
                ),
                encoding="utf-8",
            )
            campaign_path.write_bytes(canonical_json_bytes(public))
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            promoted = promote(
                judge_path=judge_path,
                campaign_report_path=campaign_path,
                public_output_path=output_path,
                workflow_receipt_path=workflow_path,
                artifact_receipt_path=artifact_path,
                repository="o/r",
                release_tag="hackathon-v14",
            )
            output = output_path.read_bytes()
            self.assertEqual(promoted["schema_version"], 9)
            self.assertEqual(promoted["release_envelope"]["tag"], "hackathon-v14")
            self.assertEqual(
                promoted["release_envelope"]["blind_holdout_asset_url"],
                "https://github.com/o/r/releases/download/hackathon-v14/"
                "blind-holdout-v1.json",
            )
            self.assertEqual(
                promoted["sequential_blind_campaign"]["public_sha256"],
                hashlib.sha256(output).hexdigest(),
            )

    def test_rejects_artifact_or_workflow_drift(self) -> None:
        public = _public()
        source = public["source_head"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                name: root / f"{name}.json"
                for name in ("judge", "campaign", "workflow", "artifact")
            }
            output = root / "public.json"
            paths["judge"].write_text(
                json.dumps(
                    {
                        "schema_version": 8,
                        "public_demo": {"url": "https://demo.example.test/"},
                        "release_envelope": {},
                    }
                ),
                encoding="utf-8",
            )
            paths["campaign"].write_bytes(canonical_json_bytes(public))
            paths["workflow"].write_text(
                json.dumps(
                    {
                        "id": RUN_ID,
                        "run_attempt": 1,
                        "conclusion": "success",
                        "head_sha": source,
                    }
                ),
                encoding="utf-8",
            )
            paths["artifact"].write_text(
                json.dumps(
                    {
                        "id": ARTIFACT_ID,
                        "name": "continuum-sequential-blind-stale",
                        "digest": "sha256:" + ARCHIVE_SHA,
                        "expired": False,
                        "workflow_run": {"id": RUN_ID},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "exact-run"):
                promote(
                    judge_path=paths["judge"],
                    campaign_report_path=paths["campaign"],
                    public_output_path=output,
                    workflow_receipt_path=paths["workflow"],
                    artifact_receipt_path=paths["artifact"],
                    repository="o/r",
                    release_tag="hackathon-v14",
                )


if __name__ == "__main__":
    unittest.main()

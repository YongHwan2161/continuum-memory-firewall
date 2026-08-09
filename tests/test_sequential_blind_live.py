from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from continuum.blind_holdout import canonical_json_bytes
from continuum.sequential_blind import build_campaign_manifest
from scripts.score_sequential_blind import evaluate
from scripts.seal_sequential_blind_batch import seal_batch
from scripts.seal_sequential_blind_campaign import seal_campaign
from tests.test_blind_holdout_seal import FakeS3SealClient
from tests.test_sequential_blind import CAMPAIGN_ID, NOW, SOURCE_HEAD, SequentialBlindTests


class SequentialBlindLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = SequentialBlindTests(
            methodName="test_generation_forms_twelve_hidden_five_episode_chains"
        )

    def test_all_inputs_are_content_addressed_before_campaign_seal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client = FakeS3SealClient()
            commitment_paths = []
            seal_receipts = []
            for batch_index in (1, 2, 3):
                challenge, labels, commitment = self.contract.generate(batch_index)
                batch_root = root / f"batch-{batch_index}"
                batch_root.mkdir()
                for name, value in (
                    ("challenge", challenge),
                    ("labels", labels),
                    ("commitment", commitment),
                ):
                    (batch_root / f"{name}.json").write_bytes(
                        canonical_json_bytes(value)
                    )
                commitment_paths.append(batch_root / "commitment.json")
                seal_receipts.append(
                    seal_batch(
                        client=client,
                        bucket="private-evidence-bucket",
                        prefix=f"evidence/sequential/source/run/batch-{batch_index}",
                        challenge_path=batch_root / "challenge.json",
                        labels_path=batch_root / "labels.json",
                        commitment_path=batch_root / "commitment.json",
                        output_path=batch_root / "seal.json",
                        workflow_run_id=31310000001,
                        workflow_run_attempt=1,
                    )
                )
            manifest, campaign_receipt = seal_campaign(
                client=client,
                bucket="private-evidence-bucket",
                prefix="evidence/sequential/source/run",
                commitment_paths=commitment_paths,
                source_head=SOURCE_HEAD,
                campaign_id=CAMPAIGN_ID,
                manifest_path=root / "campaign.json",
                receipt_path=root / "campaign-receipt.json",
                workflow_run_id=31310000001,
                workflow_run_attempt=1,
            )
            self.assertEqual(len(client.objects), 10)
            self.assertEqual(len(campaign_receipt["commitment_sha256s"]), 3)
            self.assertEqual(
                campaign_receipt["campaign_manifest_sha256"],
                manifest["campaign_manifest_sha256"],
            )
            self.assertTrue(
                all(item["write_once_condition"] == "If-None-Match:*" for item in seal_receipts)
            )

    def test_packaged_sealers_support_direct_script_execution(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for name in (
            "seal_sequential_blind_batch.py",
            "seal_sequential_blind_campaign.py",
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import runpy,sys;from pathlib import Path;"
                        "sys.path.insert(0,str(Path(sys.argv[1]).parent));"
                        "runpy.run_path(sys.argv[1])"
                    ),
                    str(root / "scripts" / name),
                ],
                cwd=Path(__file__).resolve().parent,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(root / "src")},
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_evaluator_opens_labels_after_all_campaign_candidates(self) -> None:
        batches = [self.contract.generate(index) for index in (1, 2, 3)]
        challenge, labels, commitment = batches[0]
        manifest = build_campaign_manifest(
            commitments=[item[2] for item in batches],
            source_head=SOURCE_HEAD,
            campaign_id=CAMPAIGN_ID,
            created_at=NOW.isoformat(),
        )
        started = NOW + timedelta(minutes=1)
        completed = NOW + timedelta(minutes=9)
        observations = {
            "kind": "continuum.sequential-blind.observations",
            "source_head": SOURCE_HEAD,
            "deployment_artifact_sha256": "b" * 64,
            "evaluation_id": "evaluation-1",
            "campaign_id": CAMPAIGN_ID,
            "batch_index": 1,
            "generator_model": commitment["generator_model"],
            "agent_model": "amazon.nova-micro-v1:0",
            "agent_region": "ap-southeast-2",
            "embedding_model": "amazon.titan-embed-text-v2:0",
            "embedding_region": "ap-northeast-2",
            "migration_version": 35,
            "repository": "owner/repository",
            "workflow": {
                "run_id": 31310000001,
                "run_attempt": 1,
                "started_at": started.isoformat(),
                "completed_at": completed.isoformat(),
            },
            "seal_receipt": {
                "sealed_at": (NOW + timedelta(seconds=30)).isoformat(),
                "commitment_sha256": commitment["commitment_sha256"],
            },
            "campaign_seal_receipt": {
                "sealed_at": NOW.isoformat(),
                "campaign_manifest_sha256": manifest["campaign_manifest_sha256"],
            },
            "candidate_process_opened_labels": False,
            "candidate_process_opened_campaign_manifest": False,
            "candidate_input_contract": "challenge-commitment-and-seal-receipts-only",
            "provider_capability_manifests": {
                "github": {"supports_idempotency": True},
                "s3": {"supports_idempotency": True},
            },
            "observations": self.contract.observations(
                challenge, labels, batch_index=1
            ),
        }
        report, public, receipt = evaluate(
            challenge=challenge,
            labels=labels,
            commitment=commitment,
            observations=observations,
            campaign_manifest=manifest,
            campaign_commitments=[item[2] for item in batches],
            labels_opened_after_campaign_completed_at=(
                completed + timedelta(minutes=20)
            ).isoformat(),
        )
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertTrue(
            report["evaluator"][
                "opened_labels_after_all_campaign_candidates_completed"
            ]
        )
        self.assertEqual(public["kind"], "continuum.sequential-blind.batch-report")
        self.assertEqual(len(receipt["report_sha256"]), 64)
        self.assertEqual(
            json.loads(canonical_json_bytes(receipt)), receipt
        )


if __name__ == "__main__":
    unittest.main()

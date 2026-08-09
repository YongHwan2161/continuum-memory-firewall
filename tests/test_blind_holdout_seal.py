from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from continuum.blind_holdout import canonical_json_bytes, generate_blind_holdout
from scripts.seal_blind_holdout import seal
from tests.test_blind_holdout import FakeGenerator


class FakeS3SealClient:
    def __init__(self) -> None:
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, Metadata, ServerSideEncryption, **kwargs):
        self.objects[(Bucket, Key)] = {
            "body": bytes(Body),
            "metadata": dict(Metadata),
            "sse": ServerSideEncryption,
        }
        return {"ETag": f'"etag-{len(self.objects)}"'}

    def get_object(self, *, Bucket, Key):
        value = self.objects[(Bucket, Key)]
        return {
            "Body": BytesIO(value["body"]),
            "Metadata": value["metadata"],
            "ServerSideEncryption": value["sse"],
            "ETag": '"sealed-etag"',
        }


class BlindHoldoutSealTests(unittest.TestCase):
    def test_content_addressed_inputs_are_sealed_before_execution(self) -> None:
        challenge, labels, commitment = generate_blind_holdout(
            client=FakeGenerator(),
            model_id="amazon.nova-micro-v1:0",
            source_head="a" * 40,
            generation_nonce="workflow-31270000000-attempt-1",
            generated_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for name, value in (
                ("challenge", challenge),
                ("labels", labels),
                ("commitment", commitment),
            ):
                path = root / f"{name}.json"
                path.write_bytes(canonical_json_bytes(value))
                paths[name] = path
            output = root / "receipt.json"
            client = FakeS3SealClient()
            receipt = seal(
                client=client,
                bucket="private-evidence-bucket",
                prefix="evidence/blind/source/run",
                challenge_path=paths["challenge"],
                labels_path=paths["labels"],
                commitment_path=paths["commitment"],
                output_path=output,
                workflow_run_id=31270000000,
                workflow_run_attempt=1,
            )
            self.assertEqual(len(client.objects), 3)
            self.assertEqual(receipt["write_once_condition"], "If-None-Match:*")
            self.assertIn(commitment["challenge_sha256"], receipt["objects"]["challenge"]["key"])
            self.assertIn(commitment["labels_sha256"], receipt["objects"]["labels"]["key"])
            self.assertEqual(json.loads(output.read_text())["receipt_sha256"], receipt["receipt_sha256"])


if __name__ == "__main__":
    unittest.main()

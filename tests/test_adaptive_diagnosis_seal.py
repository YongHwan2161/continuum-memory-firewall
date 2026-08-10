from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from continuum.adaptive_diagnosis import generate_adaptive_diagnosis_inputs
from continuum.blind_holdout import canonical_json_bytes
from scripts.run_live_adaptive_diagnosis import _validate_seal
from scripts.seal_adaptive_diagnosis import seal


class FakeS3:
    def __init__(self) -> None:
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, Metadata, ServerSideEncryption, **kwargs):
        self.objects[(Bucket, Key)] = {
            "body": bytes(Body),
            "metadata": dict(Metadata),
            "sse": ServerSideEncryption,
        }
        return {"ETag": '"etag"'}

    def get_object(self, *, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        return {
            "Body": BytesIO(item["body"]),
            "Metadata": item["metadata"],
            "ServerSideEncryption": item["sse"],
            "ETag": '"etag"',
        }


class AdaptiveDiagnosisSealTests(unittest.TestCase):
    def test_challenge_labels_and_commitment_are_write_once(self) -> None:
        values = generate_adaptive_diagnosis_inputs(
            source_head="a" * 40,
            generation_nonce="workflow-31399999999-attempt-1",
            generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name, value in zip(("challenge", "labels", "commitment"), values):
                path = root / f"{name}.json"
                path.write_bytes(canonical_json_bytes(value))
                paths.append(path)
            output = root / "seal.json"
            client = FakeS3()
            receipt = seal(
                client=client,
                bucket="private-evidence",
                prefix="evidence/adaptive/source/run",
                challenge_path=paths[0],
                labels_path=paths[1],
                commitment_path=paths[2],
                output_path=output,
                workflow_run_id=31399999999,
                workflow_run_attempt=1,
            )
            self.assertEqual(len(client.objects), 3)
            self.assertEqual(receipt["write_once_condition"], "If-None-Match:*")
            self.assertEqual(
                receipt["commitment_sha256"], values[2]["commitment_sha256"]
            )
            self.assertEqual(
                json.loads(output.read_text())["receipt_sha256"],
                receipt["receipt_sha256"],
            )
            _validate_seal(
                challenge=values[0],
                labels=values[1],
                commitment=values[2],
                seal_receipt=receipt,
            )


if __name__ == "__main__":
    unittest.main()

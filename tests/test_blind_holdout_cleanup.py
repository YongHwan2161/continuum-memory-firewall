import unittest

from scripts.cleanup_blind_holdout import cleanup


class FakeS3Cleanup:
    def __init__(self) -> None:
        self.objects = {
            "blind-holdout-sandbox/blind-31297826742-1/a.json",
            "blind-holdout-sandbox/blind-31297826742-1/b.json",
            "different-prefix/preserve.json",
        }

    def list_objects_v2(self, *, Bucket, Prefix, **kwargs):
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        return {
            "Contents": [{"Key": key} for key in keys],
            "IsTruncated": False,
            "KeyCount": len(keys),
        }

    def delete_objects(self, *, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.discard(item["Key"])
        return {}


class BlindHoldoutCleanupTests(unittest.TestCase):
    def test_cleanup_deletes_only_the_exact_bounded_prefix_and_proves_zero(self) -> None:
        client = FakeS3Cleanup()
        receipt = cleanup(
            client=client,
            bucket="continuum-hackathon-722ccf43755f",
            prefix="blind-holdout-sandbox/blind-31297826742-1",
        )
        self.assertEqual(receipt["deleted_count"], 2)
        self.assertEqual(receipt["residual_count"], 0)
        self.assertEqual(client.objects, {"different-prefix/preserve.json"})

    def test_cleanup_rejects_a_prefix_outside_the_holdout_namespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            cleanup(
                client=FakeS3Cleanup(),
                bucket="continuum-hackathon-722ccf43755f",
                prefix="evidence/blind-holdout",
            )


if __name__ == "__main__":
    unittest.main()

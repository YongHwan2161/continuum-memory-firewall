import unittest

from scripts.run_github_release_fault_matrix import ProviderError, run_matrix


class FakeProvider:
    def __init__(self) -> None:
        self.release = None
        self.next_asset = 10
        self._assets = []

    def create_draft(self, *, tag, target):
        self.release = {
            "id": 7,
            "tag_name": tag,
            "target_commitish": target,
            "draft": True,
        }
        return dict(self.release)

    def releases(self):
        return [] if self.release is None else [dict(self.release)]

    def assets(self, release_id):
        self.assert_release(release_id)
        return [dict(item) for item in self._assets]

    def upload(self, release_id, name, body):
        self.assert_release(release_id)
        if any(item["name"] == name for item in self._assets):
            raise ProviderError(422, "already exists")
        import hashlib

        item = {
            "id": self.next_asset,
            "name": name,
            "digest": "sha256:" + hashlib.sha256(body).hexdigest(),
        }
        self.next_asset += 1
        self._assets.append(item)
        return dict(item)

    def delete(self, release_id):
        self.assert_release(release_id)
        self.release = None
        self._assets = []

    def tag_ref_exists(self, tag):
        return False

    def assert_release(self, release_id):
        if self.release is None or self.release["id"] != release_id:
            raise AssertionError("release not found")


class GitHubReleaseFaultMatrixTests(unittest.TestCase):
    def test_disposable_matrix_recovers_and_cleans_every_boundary(self):
        report = run_matrix(
            FakeProvider(),
            repository="owner/repository",
            tag="sandbox-release-tx-1",
            target="a" * 40,
        )
        self.assertEqual(report["gate"]["status"], "PASS")
        self.assertEqual(len(report["scenarios"]), 5)
        self.assertEqual(report["author_attestation_count"], 0)
        self.assertEqual(report["published_release_count"], 0)
        self.assertTrue(report["gate"]["draft_and_tag_removed"])


if __name__ == "__main__":
    unittest.main()

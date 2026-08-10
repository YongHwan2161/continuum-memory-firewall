from email.message import Message
from http.client import RemoteDisconnected
from unittest.mock import MagicMock, patch
import unittest
from urllib.error import HTTPError

from scripts.run_live_ci_recovery import GitHubActionsProvider, GitHubAPIError


class GitHubActionsProviderArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = GitHubActionsProvider(
            repository="owner/repository",
            token="test-token",
            source_head="a" * 40,
            ref="main",
        )

    @staticmethod
    def redirect() -> HTTPError:
        headers = Message()
        headers["Location"] = "https://objects.example.test/signed-artifact"
        return HTTPError(
            "https://api.github.test/artifact",
            302,
            "Found",
            headers,
            None,
        )

    def test_transient_redirect_disconnect_retries_only_the_read(self) -> None:
        opener = MagicMock()
        opener.open.side_effect = [RemoteDisconnected(), self.redirect()]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"archive-bytes"
        with (
            patch(
                "scripts.run_live_ci_recovery.build_opener",
                return_value=opener,
            ),
            patch(
                "scripts.run_live_ci_recovery.urlopen",
                return_value=response,
            ) as unsigned,
            patch("scripts.run_live_ci_recovery.time.sleep") as sleep,
        ):
            archive = self.provider._download_artifact_archive(123)
        self.assertEqual(archive, b"archive-bytes")
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(1)
        request = unsigned.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)

    def test_three_transport_failures_stop_without_unbounded_retry(self) -> None:
        opener = MagicMock()
        opener.open.side_effect = [
            RemoteDisconnected(),
            RemoteDisconnected(),
            RemoteDisconnected(),
        ]
        with (
            patch(
                "scripts.run_live_ci_recovery.build_opener",
                return_value=opener,
            ),
            patch("scripts.run_live_ci_recovery.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(GitHubAPIError, "three attempts"):
                self.provider._download_artifact_archive(123)
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])


if __name__ == "__main__":
    unittest.main()

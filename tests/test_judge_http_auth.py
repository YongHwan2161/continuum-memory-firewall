import os
import unittest
from unittest.mock import patch

from scripts.judge_readonly_verify import _get_bytes


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return b"{}"


class JudgeHttpAuthenticationTests(unittest.TestCase):
    def test_ephemeral_token_is_scoped_to_api_github_com(self) -> None:
        requests = []

        def open_request(request, timeout):
            requests.append((request, timeout))
            return _Response()

        with patch.dict(os.environ, {"GITHUB_TOKEN": "ephemeral-test-token"}), patch(
            "scripts.judge_readonly_verify.urlopen", side_effect=open_request
        ):
            _get_bytes("https://api.github.com/repos/o/r/actions/runs/1")
            _get_bytes("https://example.test/evidence.json")

        self.assertEqual(
            requests[0][0].get_header("Authorization"),
            "Bearer ephemeral-test-token",
        )
        self.assertIsNone(requests[1][0].get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()

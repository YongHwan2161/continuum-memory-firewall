import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from scripts.verify_network_sign_once import verify_network_sign_once


class NetworkSignOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = "owner/repository"
        self.tag = "hackathon-v8"
        self.source_digest = "a" * 40
        self.envelope = b'{"schema_version":2}\n'
        self.bundle = b'{"mediaType":"application/vnd.dev.sigstore.bundle.v0.3+json"}\n'
        self.envelope_digest = hashlib.sha256(self.envelope).hexdigest()
        self.bundle_digest = hashlib.sha256(self.bundle).hexdigest()
        self.release_url = (
            "https://api.github.com/repos/owner/repository/releases/tags/"
            "hackathon-v8"
        )
        self.envelope_url = "https://downloads.example.test/envelope.json"
        self.bundle_url = "https://downloads.example.test/envelope.sigstore.jsonl"
        self.attestation_url = (
            "https://api.github.com/repos/owner/repository/attestations/"
            f"sha256:{self.envelope_digest}"
        )
        self.release = {
            "immutable": True,
            "draft": False,
            "tag_name": self.tag,
            "target_commitish": self.source_digest,
            "assets": [
                {
                    "name": "continuum-release-envelope-v2.json",
                    "state": "uploaded",
                    "digest": f"sha256:{self.envelope_digest}",
                    "browser_download_url": self.envelope_url,
                },
                {
                    "name": "continuum-release-envelope-v2.sigstore.jsonl",
                    "state": "uploaded",
                    "digest": f"sha256:{self.bundle_digest}",
                    "browser_download_url": self.bundle_url,
                },
            ],
        }

    def _fetch_json(self, url):
        if url == self.release_url:
            return self.release
        if url == self.attestation_url:
            return {"attestations": [{"bundle_url": "https://sigstore.test/1"}]}
        raise AssertionError(url)

    def _fetch_bytes(self, url):
        if url == self.envelope_url:
            return self.envelope
        if url == self.bundle_url:
            return self.bundle
        raise AssertionError(url)

    def _run(self, command):
        self.assertIn("--deny-self-hosted-runners", command)
        self.assertEqual(command[command.index("--source-digest") + 1], self.source_digest)
        signer = "owner/repository/.github/workflows/release-envelope.yml"
        output = [
            {
                "verificationResult": {
                    "signature": {
                        "certificate": {
                            "subjectAlternativeName": (
                                f"https://github.com/{signer}@refs/heads/main"
                            ),
                            "githubWorkflowRepository": self.repository,
                            "githubWorkflowRef": "refs/heads/main",
                            "sourceRepositoryDigest": self.source_digest,
                            "sourceRepositoryRef": "refs/heads/main",
                            "issuer": "https://token.actions.githubusercontent.com",
                            "runnerEnvironment": "github-hosted",
                            "sourceRepositoryVisibilityAtSigning": "public",
                        }
                    },
                    "verifiedTimestamps": [
                        {"type": "Tlog", "uri": "https://rekor.sigstore.dev"}
                    ],
                    "statement": {
                        "subject": [
                            {
                                "name": "continuum-release-envelope-v2.json",
                                "digest": {"sha256": self.envelope_digest},
                            }
                        ]
                    },
                }
            }
        ]
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    def _verify(self):
        return verify_network_sign_once(
            repository=self.repository,
            release_tag=self.tag,
            signer_workflow=(
                "owner/repository/.github/workflows/release-envelope.yml"
            ),
            fetch_json=self._fetch_json,
            fetch_bytes=self._fetch_bytes,
            run_command=self._run,
        )

    def test_exact_single_attestation_passes(self) -> None:
        report = self._verify()
        self.assertTrue(report["ok"])
        self.assertEqual(report["attestation_count"], 1)
        self.assertTrue(report["checks"]["cryptographic_verification_passed"])

    def test_second_attestation_fails_sign_once_gate(self) -> None:
        original = self._fetch_json

        def duplicated(url):
            value = original(url)
            if url == self.attestation_url:
                return {"attestations": [{}, {}]}
            return value

        report = verify_network_sign_once(
            repository=self.repository,
            release_tag=self.tag,
            signer_workflow=(
                "owner/repository/.github/workflows/release-envelope.yml"
            ),
            fetch_json=duplicated,
            fetch_bytes=self._fetch_bytes,
            run_command=self._run,
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["exactly_one_network_attestation"])

    def test_tampered_network_bundle_fails_digest_gate(self) -> None:
        def tampered(url):
            if url == self.bundle_url:
                return self.bundle + b"tampered"
            return self._fetch_bytes(url)

        report = verify_network_sign_once(
            repository=self.repository,
            release_tag=self.tag,
            signer_workflow=(
                "owner/repository/.github/workflows/release-envelope.yml"
            ),
            fetch_json=self._fetch_json,
            fetch_bytes=tampered,
            run_command=self._run,
        )
        self.assertFalse(report["ok"])
        self.assertFalse(
            report["checks"]["release_asset_digests_match_network_bytes"]
        )

    def test_release_workflow_owns_the_only_signing_path(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        release_workflow = (
            repository_root / ".github" / "workflows" / "release-envelope.yml"
        ).read_text(encoding="utf-8")
        pages_workflow = (
            repository_root / ".github" / "workflows" / "pages.yml"
        ).read_text(encoding="utf-8")

        self.assertEqual(release_workflow.count("uses: actions/attest@v4"), 1)
        self.assertIn("Refuse a second envelope signature", release_workflow)
        self.assertIn("--deny-self-hosted-runners", release_workflow)
        self.assertIn("continuum-release-envelope-v2.sigstore.jsonl", release_workflow)
        self.assertFalse(
            (
                repository_root
                / ".github"
                / "workflows"
                / "attest-release-envelope.yml"
            ).exists()
        )
        self.assertIn("release:\n    types:\n      - published", pages_workflow)
        self.assertIn("Materialize the signed envelope bundle", pages_workflow)


if __name__ == "__main__":
    unittest.main()

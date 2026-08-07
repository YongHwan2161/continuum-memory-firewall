import base64
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from scripts.verify_network_sign_once import verify_network_sign_once


class NetworkSignOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = "owner/repository"
        self.tag = "hackathon-v10"
        self.source_digest = "a" * 40
        self.envelope = b'{"schema_version":2}\n'
        self.envelope_digest = hashlib.sha256(self.envelope).hexdigest()
        self.release_url = (
            "https://api.github.com/repos/owner/repository/releases/tags/"
            "hackathon-v10"
        )
        self.envelope_url = "https://downloads.example.test/envelope.json"
        self.author_bundle_url = (
            "https://downloads.example.test/envelope.sigstore.jsonl"
        )
        self.author_api_bundle_url = "https://sigstore.test/author"
        self.platform_api_bundle_url = "https://sigstore.test/platform"
        self.network_bundle_public_url = (
            "https://demo.example.test/network-attestations.jsonl"
        )
        self.attestation_url = (
            "https://api.github.com/repos/owner/repository/attestations/"
            f"sha256:{self.envelope_digest}"
        )
        self.author_bundle = self._bundle(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [
                    {
                        "name": "continuum-release-envelope-v2.json",
                        "digest": {"sha256": self.envelope_digest},
                    }
                ],
                "predicateType": "https://slsa.dev/provenance/v1",
                "predicate": {},
            },
            rekor=True,
        )
        self.platform_bundle = self._bundle(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [
                    {
                        "uri": f"pkg:github/{self.repository}@{self.tag}",
                        "digest": {"sha1": self.source_digest},
                    },
                    {
                        "name": "continuum-release-envelope-v2.json",
                        "digest": {"sha256": self.envelope_digest},
                    },
                ],
                "predicateType": (
                    "https://in-toto.io/attestation/release/v0.2"
                ),
                "predicate": {"tag": self.tag},
            },
            timestamp=True,
        )
        self.author_bundle_bytes = (
            json.dumps(self.author_bundle, separators=(",", ":")).encode()
            + b"\n"
        )
        self.platform_bundle_bytes = (
            json.dumps(self.platform_bundle, separators=(",", ":")).encode()
            + b"\n"
        )
        self.network_bundle_bytes = (
            self.platform_bundle_bytes + self.author_bundle_bytes
        )
        self.author_bundle_digest = hashlib.sha256(
            self.author_bundle_bytes
        ).hexdigest()
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
                    "digest": f"sha256:{self.author_bundle_digest}",
                    "browser_download_url": self.author_bundle_url,
                },
            ],
        }

    @staticmethod
    def _bundle(statement, *, rekor=False, timestamp=False):
        material = {"certificate": {"rawBytes": "certificate"}}
        if rekor:
            material["tlogEntries"] = [
                {
                    "inclusionProof": {
                        "checkpoint": {
                            "envelope": "rekor.sigstore.dev checkpoint"
                        }
                    }
                }
            ]
        if timestamp:
            material["timestampVerificationData"] = {
                "rfc3161Timestamps": [{"signedTimestamp": "timestamp"}]
            }
        return {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "verificationMaterial": material,
            "dsseEnvelope": {
                "payload": base64.b64encode(
                    json.dumps(statement, separators=(",", ":")).encode()
                ).decode(),
                "payloadType": "application/vnd.in-toto+json",
                "signatures": [{"sig": "signature"}],
            },
        }

    def _fetch_json(self, url):
        if url == self.release_url:
            return self.release
        if url == self.attestation_url:
            return {
                "attestations": [
                    {"bundle_url": self.platform_api_bundle_url},
                    {"bundle_url": self.author_api_bundle_url},
                ]
            }
        raise AssertionError(url)

    def _fetch_bytes(self, url):
        if url == self.envelope_url:
            return self.envelope
        if url in {self.author_bundle_url, self.author_api_bundle_url}:
            return self.author_bundle_bytes
        if url == self.platform_api_bundle_url:
            return self.platform_bundle_bytes
        if url == self.network_bundle_public_url:
            return self.network_bundle_bytes
        raise AssertionError(url)

    def _run(self, command):
        self.assertIn("--deny-self-hosted-runners", command)
        self.assertEqual(
            command[command.index("--source-digest") + 1], self.source_digest
        )
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
                            "issuer": (
                                "https://token.actions.githubusercontent.com"
                            ),
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

    def _download_bundles(self, repository, asset_name, envelope_bytes):
        self.assertEqual(repository, self.repository)
        self.assertEqual(asset_name, "continuum-release-envelope-v2.json")
        self.assertEqual(envelope_bytes, self.envelope)
        return [self.platform_bundle, self.author_bundle]

    def _verify(self):
        return verify_network_sign_once(
            repository=self.repository,
            release_tag=self.tag,
            signer_workflow=(
                "owner/repository/.github/workflows/release-envelope.yml"
            ),
            network_bundle_public_url=self.network_bundle_public_url,
            fetch_json=self._fetch_json,
            fetch_bytes=self._fetch_bytes,
            download_bundles=self._download_bundles,
            run_command=self._run,
        )

    def test_one_author_and_one_platform_attestation_pass(self) -> None:
        report = self._verify()
        self.assertTrue(report["ok"])
        self.assertEqual(report["attestation_count"], 2)
        self.assertEqual(report["author_attestation_count"], 1)
        self.assertEqual(report["platform_attestation_count"], 1)
        self.assertTrue(
            report["checks"]["author_cryptographic_verification_passed"]
        )

    def test_second_author_attestation_fails_sign_once_gate(self) -> None:
        original = self._fetch_json

        def duplicated(url):
            value = original(url)
            if url == self.attestation_url:
                value["attestations"].append(
                    {"bundle_url": self.author_api_bundle_url}
                )
            return value

        report = verify_network_sign_once(
            repository=self.repository,
            release_tag=self.tag,
            signer_workflow=(
                "owner/repository/.github/workflows/release-envelope.yml"
            ),
            network_bundle_public_url=self.network_bundle_public_url,
            fetch_json=duplicated,
            fetch_bytes=self._fetch_bytes,
            download_bundles=lambda *_args: [
                self.platform_bundle,
                self.author_bundle,
                self.author_bundle,
            ],
            run_command=self._run,
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["exactly_one_author_attestation"])

    def test_tampered_author_bundle_fails_digest_gate(self) -> None:
        def tampered(url):
            if url == self.author_bundle_url:
                return self.author_bundle_bytes + b" "
            return self._fetch_bytes(url)

        report = verify_network_sign_once(
            repository=self.repository,
            release_tag=self.tag,
            signer_workflow=(
                "owner/repository/.github/workflows/release-envelope.yml"
            ),
            network_bundle_public_url=self.network_bundle_public_url,
            fetch_json=self._fetch_json,
            fetch_bytes=tampered,
            download_bundles=self._download_bundles,
            run_command=self._run,
        )
        self.assertFalse(report["ok"])
        self.assertFalse(
            report["checks"]["release_asset_digests_match_network_bytes"]
        )

    def test_release_workflow_owns_the_only_author_signing_path(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        release_workflow = (
            repository_root / ".github" / "workflows" / "release-envelope.yml"
        ).read_text(encoding="utf-8")
        pages_workflow = (
            repository_root / ".github" / "workflows" / "pages.yml"
        ).read_text(encoding="utf-8")

        self.assertEqual(release_workflow.count("uses: actions/attest@v4"), 1)
        self.assertIn(
            "Reconcile the author attestation before signing",
            release_workflow,
        )
        self.assertIn("Create the durable draft before author signing", release_workflow)
        self.assertIn("release_transaction_coordinator.py", release_workflow)
        self.assertIn("cancel-in-progress: false", release_workflow)
        self.assertIn("releases?per_page=100", release_workflow)
        self.assertNotIn("--slurp", release_workflow)
        self.assertIn("uploads.github.com", release_workflow)
        self.assertNotIn(
            'repos/$GITHUB_REPOSITORY/releases/tags/$RELEASE_TAG',
            release_workflow,
        )
        self.assertIn("required", release_workflow)
        self.assertIn("--deny-self-hosted-runners", release_workflow)
        self.assertIn("continuum-release-envelope-v2.sigstore.jsonl", release_workflow)
        self.assertIn("attestations/sha1:$GITHUB_SHA", release_workflow)
        self.assertIn("actions: write", release_workflow)
        self.assertIn("gh workflow run pages.yml --ref main", release_workflow)
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
        self.assertIn("PAGES_MATERIALIZED", pages_workflow)
        self.assertIn("Verify the materialized transaction receipt", pages_workflow)


if __name__ == "__main__":
    unittest.main()

"""Verify one network-visible Sigstore attestation for a release envelope."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Callable, Sequence
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


DEFAULT_REPOSITORY = "YongHwan2161/continuum-memory-firewall"
DEFAULT_RELEASE_TAG = "hackathon-v8"
DEFAULT_ASSET_NAME = "continuum-release-envelope-v2.json"
DEFAULT_BUNDLE_ASSET_NAME = "continuum-release-envelope-v2.sigstore.jsonl"
DEFAULT_SIGNER_WORKFLOW = (
    "YongHwan2161/continuum-memory-firewall/"
    ".github/workflows/release-envelope.yml"
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_RESPONSE_BYTES = 10_000_000


def _require_https(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username:
        raise RuntimeError("network sign-once verification permits HTTPS only")


def _get_bytes(url: str, *, timeout: float = 15.0) -> bytes:
    _require_https(url)
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json,application/octet-stream",
            "User-Agent": "continuum-network-sign-once/1",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("network sign-once response exceeded the size limit")
    return body


def _get_json(url: str) -> dict[str, Any]:
    value = json.loads(_get_bytes(url).decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("expected a JSON object")
    return value


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def verify_network_sign_once(
    *,
    repository: str = DEFAULT_REPOSITORY,
    release_tag: str = DEFAULT_RELEASE_TAG,
    asset_name: str = DEFAULT_ASSET_NAME,
    bundle_asset_name: str = DEFAULT_BUNDLE_ASSET_NAME,
    signer_workflow: str = DEFAULT_SIGNER_WORKFLOW,
    fetch_json: Callable[[str], dict[str, Any]] = _get_json,
    fetch_bytes: Callable[[str], bytes] = _get_bytes,
    run_command: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = _run,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise RuntimeError("repository must use owner/name syntax")
    release_api_url = (
        f"https://api.github.com/repos/{repository}/releases/tags/"
        f"{quote(release_tag, safe='')}"
    )
    release = fetch_json(release_api_url)
    assets = {
        item.get("name"): item
        for item in release.get("assets", [])
        if isinstance(item, dict)
    }
    envelope_asset = assets.get(asset_name, {})
    bundle_asset = assets.get(bundle_asset_name, {})
    envelope_digest = str(envelope_asset.get("digest", "")).removeprefix(
        "sha256:"
    )
    bundle_digest = str(bundle_asset.get("digest", "")).removeprefix(
        "sha256:"
    )
    source_digest = str(release.get("target_commitish", ""))
    if not SHA_PATTERN.fullmatch(source_digest):
        raise RuntimeError("release target is not an exact commit SHA")
    if not SHA256_PATTERN.fullmatch(envelope_digest):
        raise RuntimeError("release envelope digest is invalid")
    if not SHA256_PATTERN.fullmatch(bundle_digest):
        raise RuntimeError("release bundle digest is invalid")
    envelope_url = str(envelope_asset.get("browser_download_url", ""))
    bundle_url = str(bundle_asset.get("browser_download_url", ""))
    envelope_bytes = fetch_bytes(envelope_url)
    bundle_bytes = fetch_bytes(bundle_url)
    envelope_hash = hashlib.sha256(envelope_bytes).hexdigest()
    bundle_hash = hashlib.sha256(bundle_bytes).hexdigest()

    attestation_api_url = (
        f"https://api.github.com/repos/{repository}/attestations/"
        f"sha256:{envelope_digest}"
    )
    attestation_index = fetch_json(attestation_api_url)
    attestations = attestation_index.get("attestations", [])
    if not isinstance(attestations, list):
        attestations = []

    with TemporaryDirectory() as directory:
        envelope_path = Path(directory) / asset_name
        bundle_path = Path(directory) / bundle_asset_name
        envelope_path.write_bytes(envelope_bytes)
        bundle_path.write_bytes(bundle_bytes)
        result = run_command(
            [
                "gh",
                "attestation",
                "verify",
                str(envelope_path),
                "--repo",
                repository,
                "--bundle",
                str(bundle_path),
                "--signer-workflow",
                signer_workflow,
                "--source-ref",
                "refs/heads/main",
                "--source-digest",
                source_digest,
                "--deny-self-hosted-runners",
                "--format",
                "json",
            ]
        )
    verified: list[dict[str, Any]] = []
    if result.returncode == 0:
        parsed = json.loads(result.stdout)
        if isinstance(parsed, list):
            verified = [item for item in parsed if isinstance(item, dict)]

    verification = verified[0].get("verificationResult", {}) if len(verified) == 1 else {}
    certificate = verification.get("signature", {}).get("certificate", {})
    statement = verification.get("statement", {})
    subjects = statement.get("subject", [])
    timestamps = verification.get("verifiedTimestamps", [])
    expected_san = (
        f"https://github.com/{signer_workflow}@refs/heads/main"
    )
    checks = {
        "release_is_exact_and_immutable": (
            release.get("immutable") is True
            and release.get("draft") is False
            and release.get("tag_name") == release_tag
        ),
        "release_assets_uploaded": (
            envelope_asset.get("state") == "uploaded"
            and bundle_asset.get("state") == "uploaded"
        ),
        "release_asset_digests_match_network_bytes": (
            envelope_hash == envelope_digest and bundle_hash == bundle_digest
        ),
        "exactly_one_network_attestation": len(attestations) == 1,
        "cryptographic_verification_passed": result.returncode == 0 and len(verified) == 1,
        "subject_is_exact_release_envelope": (
            len(subjects) == 1
            and subjects[0].get("name") == asset_name
            and subjects[0].get("digest", {}).get("sha256") == envelope_digest
        ),
        "signer_identity_is_exact_main_workflow": (
            certificate.get("subjectAlternativeName") == expected_san
            and certificate.get("githubWorkflowRepository") == repository
            and certificate.get("githubWorkflowRef") == "refs/heads/main"
            and certificate.get("sourceRepositoryDigest") == source_digest
            and certificate.get("sourceRepositoryRef") == "refs/heads/main"
        ),
        "github_hosted_public_oidc_identity": (
            certificate.get("issuer")
            == "https://token.actions.githubusercontent.com"
            and certificate.get("runnerEnvironment") == "github-hosted"
            and certificate.get("sourceRepositoryVisibilityAtSigning") == "public"
        ),
        "rekor_transparency_timestamp_verified": (
            len(timestamps) >= 1
            and any(
                item.get("type") == "Tlog"
                and item.get("uri") == "https://rekor.sigstore.dev"
                for item in timestamps
                if isinstance(item, dict)
            )
        ),
    }
    return {
        "ok": all(checks.values()),
        "mode": "network-visible-sign-once",
        "repository": repository,
        "release_tag": release_tag,
        "source_digest": source_digest,
        "envelope_sha256": envelope_digest,
        "bundle_sha256": bundle_digest,
        "attestation_count": len(attestations),
        "verified_attestation_count": len(verified),
        "checks": checks,
        "stderr": result.stderr.strip() if result.returncode else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG)
    parser.add_argument("--asset-name", default=DEFAULT_ASSET_NAME)
    parser.add_argument("--bundle-asset-name", default=DEFAULT_BUNDLE_ASSET_NAME)
    parser.add_argument("--signer-workflow", default=DEFAULT_SIGNER_WORKFLOW)
    args = parser.parse_args()
    report = verify_network_sign_once(
        repository=args.repository,
        release_tag=args.release_tag,
        asset_name=args.asset_name,
        bundle_asset_name=args.bundle_asset_name,
        signer_workflow=args.signer_workflow,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

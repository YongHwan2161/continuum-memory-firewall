"""Verify one author signature plus GitHub's immutable-release countersignature."""

from __future__ import annotations

import argparse
import base64
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
DEFAULT_RELEASE_TAG = "hackathon-v9"
DEFAULT_ASSET_NAME = "continuum-release-envelope-v2.json"
DEFAULT_AUTHOR_BUNDLE_ASSET_NAME = (
    "continuum-release-envelope-v2.sigstore.jsonl"
)
DEFAULT_NETWORK_BUNDLE_PUBLIC_URL = (
    "https://yonghwan2161.github.io/continuum-memory-firewall/evidence/"
    "continuum-release-envelope-v2.network-attestations.jsonl"
)
DEFAULT_SIGNER_WORKFLOW = (
    "YongHwan2161/continuum-memory-firewall/"
    ".github/workflows/release-envelope.yml"
)
AUTHOR_PREDICATE = "https://slsa.dev/provenance/v1"
PLATFORM_PREDICATE = "https://in-toto.io/attestation/release/v0.2"
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
            "User-Agent": "continuum-network-sign-once/2",
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
        encoding="utf-8",
    )


def _download_network_bundles(
    repository: str,
    asset_name: str,
    envelope_bytes: bytes,
) -> list[dict[str, Any]]:
    with TemporaryDirectory() as directory:
        envelope_path = Path(directory) / asset_name
        envelope_path.write_bytes(envelope_bytes)
        result = subprocess.run(
            [
                "gh",
                "attestation",
                "download",
                str(envelope_path),
                "--repo",
                repository,
            ],
            cwd=directory,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(
                "failed to download network attestations: "
                + result.stderr.strip()
            )
        bundle_files = list(Path(directory).glob("*.jsonl"))
        if len(bundle_files) != 1:
            raise RuntimeError("expected one downloaded JSONL bundle file")
        bundles: list[dict[str, Any]] = []
        for line in bundle_files[0].read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError("downloaded bundle must be a JSON object")
            bundles.append(value)
        return bundles


def _bundle_objects(payload: bytes) -> list[dict[str, Any]]:
    lines = [line for line in payload.decode("utf-8").splitlines() if line.strip()]
    bundles: list[dict[str, Any]] = []
    for line in lines:
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError("attestation bundle must be a JSON object")
        bundles.append(value)
    return bundles


def _bundle_object(payload: bytes) -> dict[str, Any]:
    bundles = _bundle_objects(payload)
    if len(bundles) != 1:
        raise RuntimeError("author bundle asset must contain one bundle")
    return bundles[0]


def _statement(bundle: dict[str, Any]) -> dict[str, Any]:
    encoded = bundle.get("dsseEnvelope", {}).get("payload", "")
    payload = base64.b64decode(encoded, validate=True)
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeError("attestation statement must be a JSON object")
    return value


def _has_subject(
    statement: dict[str, Any],
    *,
    name: str,
    algorithm: str,
    digest: str,
) -> bool:
    return any(
        isinstance(subject, dict)
        and subject.get("name") == name
        and subject.get("digest", {}).get(algorithm) == digest
        for subject in statement.get("subject", [])
    )


def verify_network_sign_once(
    *,
    repository: str = DEFAULT_REPOSITORY,
    release_tag: str = DEFAULT_RELEASE_TAG,
    asset_name: str = DEFAULT_ASSET_NAME,
    author_bundle_asset_name: str = DEFAULT_AUTHOR_BUNDLE_ASSET_NAME,
    network_bundle_public_url: str = DEFAULT_NETWORK_BUNDLE_PUBLIC_URL,
    signer_workflow: str = DEFAULT_SIGNER_WORKFLOW,
    fetch_json: Callable[[str], dict[str, Any]] = _get_json,
    fetch_bytes: Callable[[str], bytes] = _get_bytes,
    download_bundles: Callable[
        [str, str, bytes], list[dict[str, Any]]
    ] = _download_network_bundles,
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
    author_bundle_asset = assets.get(author_bundle_asset_name, {})
    envelope_digest = str(envelope_asset.get("digest", "")).removeprefix(
        "sha256:"
    )
    author_bundle_digest = str(
        author_bundle_asset.get("digest", "")
    ).removeprefix("sha256:")
    source_digest = str(release.get("target_commitish", ""))
    if not SHA_PATTERN.fullmatch(source_digest):
        raise RuntimeError("release target is not an exact commit SHA")
    if not SHA256_PATTERN.fullmatch(envelope_digest):
        raise RuntimeError("release envelope digest is invalid")
    if not SHA256_PATTERN.fullmatch(author_bundle_digest):
        raise RuntimeError("author bundle digest is invalid")

    envelope_bytes = fetch_bytes(
        str(envelope_asset.get("browser_download_url", ""))
    )
    author_bundle_bytes = fetch_bytes(
        str(author_bundle_asset.get("browser_download_url", ""))
    )
    author_bundle = _bundle_object(author_bundle_bytes)
    author_statement = _statement(author_bundle)

    attestation_api_url = (
        f"https://api.github.com/repos/{repository}/attestations/"
        f"sha256:{envelope_digest}"
    )
    attestation_index = fetch_json(attestation_api_url)
    attestations = attestation_index.get("attestations", [])
    if not isinstance(attestations, list):
        attestations = []
    if not all(
        isinstance(item, dict)
        and str(item.get("bundle_url", "")).startswith("https://")
        for item in attestations
    ):
        raise RuntimeError("attestation index contains a non-HTTPS bundle URL")
    network_bundles = download_bundles(
        repository,
        asset_name,
        envelope_bytes,
    )
    public_network_bundle_bytes = fetch_bytes(network_bundle_public_url)
    public_network_bundles = _bundle_objects(public_network_bundle_bytes)
    network_statements: list[dict[str, Any]] = []
    for bundle in network_bundles:
        network_statements.append(_statement(bundle))

    author_indexes = [
        index
        for index, statement in enumerate(network_statements)
        if statement.get("predicateType") == AUTHOR_PREDICATE
        and statement.get("subject")
        == [{"name": asset_name, "digest": {"sha256": envelope_digest}}]
    ]
    release_uri = f"pkg:github/{repository}@{release_tag}"
    platform_indexes = [
        index
        for index, statement in enumerate(network_statements)
        if statement.get("predicateType") == PLATFORM_PREDICATE
        and _has_subject(
            statement,
            name=asset_name,
            algorithm="sha256",
            digest=envelope_digest,
        )
        and any(
            isinstance(subject, dict)
            and subject.get("uri") == release_uri
            and subject.get("digest", {}).get("sha1") == source_digest
            for subject in statement.get("subject", [])
        )
    ]

    with TemporaryDirectory() as directory:
        envelope_path = Path(directory) / asset_name
        bundle_path = Path(directory) / author_bundle_asset_name
        envelope_path.write_bytes(envelope_bytes)
        bundle_path.write_bytes(author_bundle_bytes)
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

    verification = (
        verified[0].get("verificationResult", {}) if len(verified) == 1 else {}
    )
    certificate = verification.get("signature", {}).get("certificate", {})
    timestamps = verification.get("verifiedTimestamps", [])
    expected_san = f"https://github.com/{signer_workflow}@refs/heads/main"
    platform_material = (
        network_bundles[platform_indexes[0]].get("verificationMaterial", {})
        if len(platform_indexes) == 1
        else {}
    )
    checks = {
        "release_is_exact_and_immutable": (
            release.get("immutable") is True
            and release.get("draft") is False
            and release.get("tag_name") == release_tag
        ),
        "release_assets_uploaded": (
            envelope_asset.get("state") == "uploaded"
            and author_bundle_asset.get("state") == "uploaded"
        ),
        "release_asset_digests_match_network_bytes": (
            hashlib.sha256(envelope_bytes).hexdigest() == envelope_digest
            and hashlib.sha256(author_bundle_bytes).hexdigest()
            == author_bundle_digest
        ),
        "exactly_one_author_attestation": len(author_indexes) == 1,
        "exactly_one_platform_release_attestation": len(platform_indexes) == 1,
        "expected_two_network_attestations": len(attestations) == 2,
        "downloaded_bundle_count_matches_index": (
            len(network_bundles) == len(attestations)
        ),
        "public_network_bundle_matches_github_download": (
            {
                json.dumps(bundle, sort_keys=True, separators=(",", ":"))
                for bundle in public_network_bundles
            }
            == {
                json.dumps(bundle, sort_keys=True, separators=(",", ":"))
                for bundle in network_bundles
            }
            and len(public_network_bundles) == 2
        ),
        "author_bundle_is_network_indexed": (
            len(author_indexes) == 1
            and network_bundles[author_indexes[0]] == author_bundle
        ),
        "author_cryptographic_verification_passed": (
            result.returncode == 0 and len(verified) == 1
        ),
        "author_subject_is_exact_release_envelope": (
            author_statement.get("predicateType") == AUTHOR_PREDICATE
            and author_statement.get("subject")
            == [{"name": asset_name, "digest": {"sha256": envelope_digest}}]
        ),
        "author_signer_identity_is_exact_main_workflow": (
            certificate.get("subjectAlternativeName") == expected_san
            and certificate.get("githubWorkflowRepository") == repository
            and certificate.get("githubWorkflowRef") == "refs/heads/main"
            and certificate.get("sourceRepositoryDigest") == source_digest
            and certificate.get("sourceRepositoryRef") == "refs/heads/main"
        ),
        "author_github_hosted_public_oidc_identity": (
            certificate.get("issuer")
            == "https://token.actions.githubusercontent.com"
            and certificate.get("runnerEnvironment") == "github-hosted"
            and certificate.get("sourceRepositoryVisibilityAtSigning") == "public"
        ),
        "author_rekor_timestamp_verified": (
            any(
                item.get("type") == "Tlog"
                and item.get("uri") == "https://rekor.sigstore.dev"
                for item in timestamps
                if isinstance(item, dict)
            )
        ),
        "platform_countersignature_material_visible": (
            bool(platform_material.get("certificate", {}).get("rawBytes"))
            and len(
                platform_material.get("timestampVerificationData", {}).get(
                    "rfc3161Timestamps", []
                )
            )
            >= 1
        ),
    }
    return {
        "ok": all(checks.values()),
        "mode": "network-visible-sign-once-v2",
        "repository": repository,
        "release_tag": release_tag,
        "source_digest": source_digest,
        "envelope_sha256": envelope_digest,
        "author_bundle_sha256": author_bundle_digest,
        "public_network_bundle_sha256": hashlib.sha256(
            public_network_bundle_bytes
        ).hexdigest(),
        "attestation_count": len(attestations),
        "author_attestation_count": len(author_indexes),
        "platform_attestation_count": len(platform_indexes),
        "verified_author_attestation_count": len(verified),
        "checks": checks,
        "stderr": result.stderr.strip() if result.returncode else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--release-tag", default=DEFAULT_RELEASE_TAG)
    parser.add_argument("--asset-name", default=DEFAULT_ASSET_NAME)
    parser.add_argument(
        "--author-bundle-asset-name",
        default=DEFAULT_AUTHOR_BUNDLE_ASSET_NAME,
    )
    parser.add_argument(
        "--network-bundle-public-url",
        default=DEFAULT_NETWORK_BUNDLE_PUBLIC_URL,
    )
    parser.add_argument("--signer-workflow", default=DEFAULT_SIGNER_WORKFLOW)
    args = parser.parse_args()
    report = verify_network_sign_once(
        repository=args.repository,
        release_tag=args.release_tag,
        asset_name=args.asset_name,
        author_bundle_asset_name=args.author_bundle_asset_name,
        network_bundle_public_url=args.network_bundle_public_url,
        signer_workflow=args.signer_workflow,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

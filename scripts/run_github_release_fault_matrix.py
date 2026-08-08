"""Exercise reversible crash boundaries against a disposable GitHub draft."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API HTTP {status}: {message}")
        self.status = status


class GitHubReleaseProvider:
    def __init__(self, *, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/vnd.github+json",
    ) -> Any:
        request = Request(
            url,
            method=method,
            data=body,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": content_type,
                "User-Agent": "continuum-release-fault-matrix/1",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read()
                if not payload:
                    return None
                return json.loads(payload)
        except HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")[:500]
            raise ProviderError(error.code, message) from error

    def _api(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repository}/{path}"

    def create_draft(self, *, tag: str, target: str) -> Mapping[str, Any]:
        body = json.dumps(
            {
                "tag_name": tag,
                "target_commitish": target,
                "name": "Disposable release transaction fault matrix",
                "body": "Synthetic, unsigned, draft-only provider fault proof.",
                "draft": True,
                "prerelease": True,
            }
        ).encode("utf-8")
        return self._request("POST", self._api("releases"), body=body)

    def releases(self) -> list[Mapping[str, Any]]:
        value = self._request("GET", self._api("releases?per_page=100"))
        return list(value)

    def assets(self, release_id: int) -> list[Mapping[str, Any]]:
        value = self._request(
            "GET", self._api(f"releases/{release_id}/assets?per_page=100")
        )
        return list(value)

    def upload(self, release_id: int, name: str, body: bytes) -> Mapping[str, Any]:
        url = (
            f"https://uploads.github.com/repos/{self.repository}/releases/"
            f"{release_id}/assets?name={quote(name)}"
        )
        return self._request(
            "POST", url, body=body, content_type="application/octet-stream"
        )

    def delete(self, release_id: int) -> None:
        self._request("DELETE", self._api(f"releases/{release_id}"))

    def tag_ref_exists(self, tag: str) -> bool:
        try:
            self._request("GET", self._api(f"git/ref/tags/{quote(tag)}"))
            return True
        except ProviderError as error:
            if error.status == 404:
                return False
            raise


def _unique(items: list[Mapping[str, Any]], message: str) -> Mapping[str, Any]:
    if len(items) != 1:
        raise RuntimeError(message)
    return items[0]


def _retry(observe, *, attempts: int = 12, delay: float = 1.0):
    last = None
    for _attempt in range(attempts):
        last = observe()
        if last is not None:
            return last
        time.sleep(delay)
    raise RuntimeError("provider observation did not converge")


def run_matrix(
    provider: GitHubReleaseProvider,
    *,
    repository: str,
    tag: str,
    target: str,
) -> dict[str, Any]:
    release_id: int | None = None
    scenarios: list[dict[str, Any]] = []
    payload = b"continuum disposable provider crash proof\n"
    payload_digest = hashlib.sha256(payload).hexdigest()
    receipt_body = json.dumps(
        {
            "kind": "continuum.disposable-release-fault-receipt",
            "release_tag": tag,
            "release_target": target,
            "payload_sha256": payload_digest,
        },
        sort_keys=True,
    ).encode("utf-8")
    receipt_digest = hashlib.sha256(receipt_body).hexdigest()
    cleanup_verified = False
    try:
        created = provider.create_draft(tag=tag, target=target)
        release_id = int(created["id"])

        # Crash: the create response is lost before local acknowledgement.
        recovered = _retry(
            lambda: next(
                (
                    item
                    for item in provider.releases()
                    if item.get("tag_name") == tag
                    and item.get("target_commitish") == target
                    and item.get("draft") is True
                ),
                None,
            )
        )
        if int(recovered["id"]) != release_id:
            raise RuntimeError("draft recovery selected a different release")
        scenarios.append(
            {"crash_point": "AFTER_DRAFT_CREATE_BEFORE_ACK", "recovered": True}
        )

        provider.upload(release_id, "synthetic-payload.txt", payload)
        # Crash: upload response is lost before the asset is recorded locally.
        recovered_asset = _retry(
            lambda: next(
                (
                    item
                    for item in provider.assets(release_id)
                    if item.get("name") == "synthetic-payload.txt"
                ),
                None,
            )
        )
        if recovered_asset.get("digest") != f"sha256:{payload_digest}":
            raise RuntimeError("uploaded payload digest differs from provider receipt")
        scenarios.append(
            {"crash_point": "AFTER_ASSET_UPLOAD_BEFORE_ACK", "recovered": True}
        )

        duplicate_status = 0
        try:
            provider.upload(release_id, "synthetic-payload.txt", payload)
        except ProviderError as error:
            duplicate_status = error.status
        if duplicate_status != 422:
            raise RuntimeError("duplicate asset upload did not fail closed")
        matching_assets = [
            item
            for item in provider.assets(release_id)
            if item.get("name") == "synthetic-payload.txt"
        ]
        _unique(matching_assets, "duplicate upload changed asset cardinality")
        scenarios.append(
            {
                "crash_point": "DUPLICATE_ASSET_UPLOAD",
                "recovered": True,
                "provider_status": duplicate_status,
                "asset_count": 1,
            }
        )

        provider.upload(
            release_id, "sandbox-reconciliation-receipt.json", receipt_body
        )
        recovered_receipt = _retry(
            lambda: next(
                (
                    item
                    for item in provider.assets(release_id)
                    if item.get("name") == "sandbox-reconciliation-receipt.json"
                ),
                None,
            )
        )
        if recovered_receipt.get("digest") != f"sha256:{receipt_digest}":
            raise RuntimeError("reconciliation receipt digest differs")
        scenarios.append(
            {"crash_point": "AFTER_RECEIPT_UPLOAD_BEFORE_ACK", "recovered": True}
        )

        provider.delete(release_id)
        # Crash: delete response is lost before cleanup acknowledgement.
        _retry(
            lambda: True
            if not any(
                item.get("id") == release_id for item in provider.releases()
            )
            else None
        )
        release_id = None
        if provider.tag_ref_exists(tag):
            raise RuntimeError("draft sandbox unexpectedly created a tag ref")
        cleanup_verified = True
        scenarios.append(
            {"crash_point": "AFTER_DELETE_BEFORE_ACK", "recovered": True}
        )
    finally:
        if release_id is not None:
            provider.delete(release_id)
            cleanup_verified = not any(
                item.get("id") == release_id for item in provider.releases()
            )

    gate = {
        "status": "PASS"
        if cleanup_verified
        and len(scenarios) == 5
        and all(item["recovered"] for item in scenarios)
        else "FAIL",
        "all_crash_points_recovered": len(scenarios) == 5
        and all(item["recovered"] for item in scenarios),
        "duplicate_assets_zero": any(
            item.get("crash_point") == "DUPLICATE_ASSET_UPLOAD"
            and item.get("asset_count") == 1
            for item in scenarios
        ),
        "draft_and_tag_removed": cleanup_verified,
    }
    return {
        "schema_version": 1,
        "provider": "github-releases-draft-sandbox",
        "repository": repository,
        "release_tag": tag,
        "release_target": target,
        "synthetic_non_sensitive": True,
        "author_attestation_count": 0,
        "published_release_count": 0,
        "scenarios": scenarios,
        "gate": gate,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--release-target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GH_TOKEN is required")
    report = run_matrix(
        GitHubReleaseProvider(repository=args.repository, token=token),
        repository=args.repository,
        tag=args.release_tag,
        target=args.release_target,
    )
    if report["gate"]["status"] != "PASS":
        raise SystemExit("GitHub release fault matrix failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

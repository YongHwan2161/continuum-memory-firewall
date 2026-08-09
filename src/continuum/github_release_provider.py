"""Bounded GitHub Releases adapter for disposable external-effect evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from continuum.episode import OutcomeStatus, ProposedAction, ProviderOutcome
from continuum.outbox import ProviderCapabilityManifest
from continuum.release_guardian import ReleaseGuardianCase


PRIMARY_ASSET_NAME = "guardian-payload.json"
RECEIPT_ASSET_NAME = "guardian-reconciliation-receipt.json"
QUARANTINED_ASSET_NAME = "quarantined-guardian-payload.json"
PRIMARY_ASSET_BODY = b'{"kind":"continuum.release-guardian","value":"expected"}\n'
CONFLICT_ASSET_BODY = b'{"kind":"continuum.release-guardian","value":"conflict"}\n'
RECEIPT_ASSET_BODY = b'{"kind":"continuum.release-guardian-receipt","status":"verified"}\n'


class GitHubProviderError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API HTTP {status}: {message}")
        self.status = status


class GitHubReleaseClient:
    """Minimal GitHub client that never exposes its bearer token."""

    def __init__(self, *, repository: str, token: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
            raise ValueError("repository must be owner/name")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self.__token = token

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
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.__token}",
                "Content-Type": content_type,
                "User-Agent": "continuum-release-guardian",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read()
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitHubProviderError(exc.code, message) from exc
        if not payload:
            return None
        return json.loads(payload)

    def _api(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repository}/{path}"

    def create_draft(self, *, tag: str, target: str) -> Mapping[str, Any]:
        payload = json.dumps(
            {
                "tag_name": tag,
                "target_commitish": target,
                "name": f"Disposable release guardian {tag}",
                "body": "Non-sensitive automated provider evaluation. Never published.",
                "draft": True,
                "prerelease": True,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request("POST", self._api("releases"), body=payload)

    def releases(self) -> list[Mapping[str, Any]]:
        value = self._request(
            "GET", self._api(f"releases?per_page=100&continuum_nonce={time.time_ns()}")
        )
        return list(value)

    def release_by_tag(self, tag: str) -> Mapping[str, Any] | None:
        return next((item for item in self.releases() if item.get("tag_name") == tag), None)

    def release(self, release_id: int) -> Mapping[str, Any] | None:
        try:
            return self._request("GET", self._api(f"releases/{release_id}"))
        except GitHubProviderError as exc:
            if exc.status == 404:
                return None
            raise

    def assets(self, release_id: int) -> list[Mapping[str, Any]]:
        value = self._request(
            "GET",
            self._api(
                f"releases/{release_id}/assets?per_page=100&continuum_nonce={time.time_ns()}"
            ),
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

    def rename_asset(self, asset_id: int, name: str) -> Mapping[str, Any]:
        body = json.dumps({"name": name}, separators=(",", ":")).encode("utf-8")
        return self._request(
            "PATCH", self._api(f"releases/assets/{asset_id}"), body=body
        )

    def delete_release(self, release_id: int) -> None:
        self._request("DELETE", self._api(f"releases/{release_id}"))

    def tag_ref_exists(self, tag: str) -> bool:
        try:
            self._request("GET", self._api(f"git/ref/tags/{quote(tag, safe='')}"))
        except GitHubProviderError as exc:
            if exc.status == 404:
                return False
            raise
        return True


@dataclass(frozen=True, slots=True)
class PreparedReleaseSandbox:
    case_id: str
    tag: str
    expected_action_type: str
    release_id: int | None


class GitHubReleaseSandboxProvider:
    """Execute only typed actions against server-owned, disposable draft releases."""

    capability_manifest = ProviderCapabilityManifest(
        supports_idempotency=True,
        receipt_lookup=True,
        reconciliation_timeout=timedelta(seconds=30),
    )

    def __init__(
        self,
        *,
        client: GitHubReleaseClient,
        release_target: str,
        run_namespace: str,
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", release_target) is None:
            raise ValueError("release target must be a full Git commit SHA")
        if re.fullmatch(r"[a-z0-9-]{6,40}", run_namespace) is None:
            raise ValueError("run namespace is invalid")
        self.client = client
        self.release_target = release_target
        self.run_namespace = run_namespace
        self._prepared: dict[str, PreparedReleaseSandbox] = {}
        self._receipts: dict[str, ProviderOutcome] = {}
        self._effects: dict[str, int] = {}

    @staticmethod
    def _asset_digest(body: bytes) -> str:
        return f"sha256:{hashlib.sha256(body).hexdigest()}"

    def _tag(self, arm: AgentArmLike, case: ReleaseGuardianCase) -> str:
        return self._tag_for_case(arm, case.case_id)

    def _tag_for_case(self, arm: AgentArmLike, case_id: str) -> str:
        case_digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:16]
        value = f"sandbox-guardian-{self.run_namespace}-{arm}-{case_digest}"
        if len(value) > 120 or re.fullmatch(r"[a-z0-9-]+", value) is None:
            raise ValueError("derived sandbox tag is invalid")
        return value

    def _remove_existing(self, tag: str) -> None:
        release = self.client.release_by_tag(tag)
        if release is not None:
            if release.get("draft") is not True:
                raise RuntimeError("sandbox tag unexpectedly names a published release")
            self.client.delete_release(int(release["id"]))
        if self.client.tag_ref_exists(tag):
            raise RuntimeError("sandbox tag unexpectedly has a Git ref")

    def _require_draft(self, prepared: PreparedReleaseSandbox) -> Mapping[str, Any]:
        release = (
            self.client.release(prepared.release_id)
            if prepared.release_id is not None
            else None
        )
        if release is None or release.get("draft") is not True:
            raise RuntimeError("expected disposable draft is absent")
        return release

    @staticmethod
    def _retry(observe, *, attempts: int = 12, delay: float = 0.5):
        last = None
        for _ in range(attempts):
            last = observe()
            if last:
                return last
            time.sleep(delay)
        raise RuntimeError("GitHub provider state did not converge")

    def prepare(
        self,
        *,
        arm: str,
        case: ReleaseGuardianCase,
    ) -> PreparedReleaseSandbox:
        tag = self._tag(arm, case)
        self._remove_existing(tag)
        expected = case.expected_action_type
        release_id = None
        if expected != "create_sandbox_draft":
            release = self.client.create_draft(tag=tag, target=self.release_target)
            release_id = int(release["id"])
            if expected in {
                "adopt_existing_asset",
                "upload_reconciliation_receipt",
            }:
                self.client.upload(release_id, PRIMARY_ASSET_NAME, PRIMARY_ASSET_BODY)
            elif expected == "quarantine_conflicting_asset":
                self.client.upload(release_id, PRIMARY_ASSET_NAME, CONFLICT_ASSET_BODY)
        prepared = PreparedReleaseSandbox(
            case_id=case.case_id,
            tag=tag,
            expected_action_type=expected,
            release_id=release_id,
        )
        self._prepared[case.case_id] = prepared
        return prepared

    def prepare_fixture(
        self, *, arm: str, case_id: str, fixture: str
    ) -> PreparedReleaseSandbox:
        """Prepare provider state from the candidate-readable fixture, not labels."""

        supported = {
            "missing-draft",
            "missing-asset",
            "lost-asset-ack",
            "missing-receipt",
            "conflicting-asset",
            "cleanup-pending",
        }
        if fixture not in supported:
            raise RuntimeError(f"unsupported GitHub holdout fixture: {fixture}")
        tag = self._tag_for_case(arm, case_id)
        self._remove_existing(tag)
        release_id = None
        if fixture != "missing-draft":
            release = self.client.create_draft(tag=tag, target=self.release_target)
            release_id = int(release["id"])
            if fixture in {"lost-asset-ack", "missing-receipt", "cleanup-pending"}:
                self.client.upload(release_id, PRIMARY_ASSET_NAME, PRIMARY_ASSET_BODY)
            elif fixture == "conflicting-asset":
                self.client.upload(release_id, PRIMARY_ASSET_NAME, CONFLICT_ASSET_BODY)
            if fixture == "cleanup-pending":
                self.client.upload(release_id, RECEIPT_ASSET_NAME, RECEIPT_ASSET_BODY)
        prepared = PreparedReleaseSandbox(
            case_id=case_id,
            tag=tag,
            expected_action_type="",
            release_id=release_id,
        )
        self._prepared[case_id] = prepared
        return prepared

    def _state(
        self, tag: str, release_id: int | None
    ) -> Mapping[str, Any]:
        release = self.client.release(release_id) if release_id is not None else None
        if release is None:
            return {"release_exists": False, "tag_ref_exists": self.client.tag_ref_exists(tag)}
        assets = self.client.assets(int(release["id"]))
        return {
            "release_exists": True,
            "release_id": int(release["id"]),
            "draft": release.get("draft") is True,
            "tag_ref_exists": self.client.tag_ref_exists(tag),
            "assets": sorted(
                [
                    {
                    "id": int(asset["id"]),
                    "name": str(asset["name"]),
                    "digest": asset.get("digest"),
                    }
                    for asset in assets
                ],
                key=lambda item: item["name"],
            ),
        }

    def execute(
        self,
        *,
        case: ReleaseGuardianCase,
        proposal: ProposedAction,
        idempotency_key: str,
        observed_at: datetime,
    ) -> ProviderOutcome:
        prior = self._receipts.get(idempotency_key)
        if prior is not None:
            return prior
        prepared = self._prepared.get(case.case_id)
        if prepared is None:
            raise RuntimeError("release sandbox was not prepared")
        before = self._state(prepared.tag, prepared.release_id)
        matched = proposal.action_type == case.expected_action_type
        effect_count = 0
        if matched:
            if proposal.action_type == "create_sandbox_draft":
                created = self.client.create_draft(
                    tag=prepared.tag, target=self.release_target
                )
                prepared = PreparedReleaseSandbox(
                    case_id=prepared.case_id,
                    tag=prepared.tag,
                    expected_action_type=prepared.expected_action_type,
                    release_id=int(created["id"]),
                )
                self._prepared[case.case_id] = prepared
                effect_count = 1
            elif proposal.action_type == "upload_release_asset":
                release = self._require_draft(prepared)
                self.client.upload(int(release["id"]), PRIMARY_ASSET_NAME, PRIMARY_ASSET_BODY)
                effect_count = 1
            elif proposal.action_type == "adopt_existing_asset":
                release = self._require_draft(prepared)
                asset = next(
                    (
                        item
                        for item in self.client.assets(int(release["id"]))
                        if item.get("name") == PRIMARY_ASSET_NAME
                    ),
                    None,
                )
                matched = asset is not None and asset.get("digest") == self._asset_digest(
                    PRIMARY_ASSET_BODY
                )
            elif proposal.action_type == "upload_reconciliation_receipt":
                release = self._require_draft(prepared)
                self.client.upload(
                    int(release["id"]), RECEIPT_ASSET_NAME, RECEIPT_ASSET_BODY
                )
                effect_count = 1
            elif proposal.action_type == "quarantine_conflicting_asset":
                release = self._require_draft(prepared)
                asset = next(
                    item
                    for item in self.client.assets(int(release["id"]))
                    if item.get("name") == PRIMARY_ASSET_NAME
                )
                self.client.rename_asset(int(asset["id"]), QUARANTINED_ASSET_NAME)
                effect_count = 1
            elif proposal.action_type == "delete_sandbox_draft":
                release = self._require_draft(prepared)
                self.client.delete_release(int(release["id"]))
                effect_count = 1
        def observe_after() -> Mapping[str, Any] | None:
            state = self._state(prepared.tag, prepared.release_id)
            return state if self._verify(case.expected_action_type, state) else None

        after = (
            self._retry(observe_after)
            if matched
            else self._state(prepared.tag, prepared.release_id)
        )
        succeeded = matched and self._verify(case.expected_action_type, after)
        state_digest = hashlib.sha256(
            json.dumps(after, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        evidence = {
            "case_id": case.case_id,
            "expected_action_type": case.expected_action_type,
            "proposed_action_type": proposal.action_type,
            "action_match": proposal.action_type == case.expected_action_type,
            "provider_state_verified": succeeded,
            "before_state_sha256": hashlib.sha256(
                json.dumps(before, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "after_state_sha256": state_digest,
            "effect_count": effect_count,
            "capability_manifest": self.capability_manifest.as_evidence(),
            "sandbox_only": True,
            "published": False,
        }
        outcome = ProviderOutcome(
            provider="github-releases-disposable-sandbox-v1",
            status=OutcomeStatus.SUCCEEDED if succeeded else OutcomeStatus.FAILED,
            evidence=evidence,
            observed_at=observed_at,
            provider_receipt_id=(
                f"github-release:{prepared.tag}:{state_digest}"
                if succeeded
                else None
            ),
            verified_at=observed_at if succeeded else None,
        )
        self._receipts[idempotency_key] = outcome
        self._effects[idempotency_key] = effect_count
        return outcome

    def execute_observed(
        self,
        *,
        case_id: str,
        proposal: ProposedAction,
        idempotency_key: str,
        observed_at: datetime,
    ) -> ProviderOutcome:
        """Execute and verify the proposed transition without an evaluation label."""

        prior = self._receipts.get(idempotency_key)
        if prior is not None:
            return prior
        prepared = self._prepared.get(case_id)
        if prepared is None:
            raise RuntimeError("release sandbox was not prepared")
        before = self._state(prepared.tag, prepared.release_id)
        action_type = proposal.action_type
        effect_count = 0
        execution_error = None
        try:
            if action_type == "create_sandbox_draft":
                created = self.client.create_draft(
                    tag=prepared.tag, target=self.release_target
                )
                prepared = PreparedReleaseSandbox(
                    case_id=prepared.case_id,
                    tag=prepared.tag,
                    expected_action_type="",
                    release_id=int(created["id"]),
                )
                self._prepared[case_id] = prepared
                effect_count = 1
            elif action_type == "upload_release_asset":
                release = self._require_draft(prepared)
                self.client.upload(int(release["id"]), PRIMARY_ASSET_NAME, PRIMARY_ASSET_BODY)
                effect_count = 1
            elif action_type == "adopt_existing_asset":
                pass
            elif action_type == "upload_reconciliation_receipt":
                release = self._require_draft(prepared)
                self.client.upload(
                    int(release["id"]), RECEIPT_ASSET_NAME, RECEIPT_ASSET_BODY
                )
                effect_count = 1
            elif action_type == "quarantine_conflicting_asset":
                release = self._require_draft(prepared)
                asset = next(
                    item
                    for item in self.client.assets(int(release["id"]))
                    if item.get("name") == PRIMARY_ASSET_NAME
                )
                self.client.rename_asset(int(asset["id"]), QUARANTINED_ASSET_NAME)
                effect_count = 1
            elif action_type == "delete_sandbox_draft":
                release = self._require_draft(prepared)
                self.client.delete_release(int(release["id"]))
                effect_count = 1
            else:
                execution_error = "ACTION_NOT_ALLOWLISTED"
        except (GitHubProviderError, RuntimeError, StopIteration) as exc:
            execution_error = type(exc).__name__
        after = self._state(prepared.tag, prepared.release_id)
        succeeded = execution_error is None and self._verify(action_type, after)
        state_digest = hashlib.sha256(
            json.dumps(after, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        evidence = {
            "case_id": case_id,
            "executed_action_type": action_type,
            "provider_state_verified": succeeded,
            "before_state_sha256": hashlib.sha256(
                json.dumps(before, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "after_state_sha256": state_digest,
            "effect_count": effect_count,
            "execution_error": execution_error,
            "capability_manifest": self.capability_manifest.as_evidence(),
            "evaluation_label_accessed": False,
            "sandbox_only": True,
            "published": False,
        }
        outcome = ProviderOutcome(
            provider="github-releases-disposable-sandbox-v1",
            status=OutcomeStatus.SUCCEEDED if succeeded else OutcomeStatus.FAILED,
            evidence=evidence,
            observed_at=observed_at,
            provider_receipt_id=(
                f"github-release:{prepared.tag}:{state_digest}" if succeeded else None
            ),
            verified_at=observed_at if succeeded else None,
        )
        self._receipts[idempotency_key] = outcome
        self._effects[idempotency_key] = effect_count
        return outcome

    @staticmethod
    def _verify(action_type: str, state: Mapping[str, Any]) -> bool:
        assets = {item["name"]: item for item in state.get("assets", [])}
        if action_type == "create_sandbox_draft":
            return state.get("release_exists") is True and state.get("draft") is True
        if action_type == "upload_release_asset":
            return assets.get(PRIMARY_ASSET_NAME, {}).get("digest") == GitHubReleaseSandboxProvider._asset_digest(PRIMARY_ASSET_BODY)
        if action_type == "adopt_existing_asset":
            return assets.get(PRIMARY_ASSET_NAME, {}).get("digest") == GitHubReleaseSandboxProvider._asset_digest(PRIMARY_ASSET_BODY)
        if action_type == "upload_reconciliation_receipt":
            return assets.get(RECEIPT_ASSET_NAME, {}).get("digest") == GitHubReleaseSandboxProvider._asset_digest(RECEIPT_ASSET_BODY)
        if action_type == "quarantine_conflicting_asset":
            return PRIMARY_ASSET_NAME not in assets and QUARANTINED_ASSET_NAME in assets
        if action_type == "delete_sandbox_draft":
            return state.get("release_exists") is False and state.get("tag_ref_exists") is False
        return False

    def cleanup(self, case_id: str) -> Mapping[str, Any]:
        prepared = self._prepared[case_id]
        release = (
            self.client.release(prepared.release_id)
            if prepared.release_id is not None
            else None
        )
        if release is not None:
            if release.get("draft") is not True:
                raise RuntimeError("cleanup refused a non-draft release")
            self.client.delete_release(int(release["id"]))
        self._retry(
            lambda: (
                (
                    prepared.release_id is None
                    or self.client.release(prepared.release_id) is None
                )
                and not self.client.tag_ref_exists(prepared.tag)
            )
        )
        residual = int(
            prepared.release_id is not None
            and self.client.release(prepared.release_id) is not None
        ) + int(self.client.tag_ref_exists(prepared.tag))
        return {
            "case_id": case_id,
            "residual_count": residual,
            "draft_removed": residual == 0,
            "published_release_count": 0,
        }

    def effect_count(self, idempotency_key: str) -> int:
        return self._effects.get(idempotency_key, 0)


AgentArmLike = str

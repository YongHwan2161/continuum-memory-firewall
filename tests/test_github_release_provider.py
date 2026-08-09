from datetime import datetime, timezone
import hashlib
import unittest

from continuum.episode import ProposedAction, RiskClass
from continuum.github_release_provider import (
    CONFLICT_ASSET_BODY,
    GitHubProviderError,
    GitHubReleaseSandboxProvider,
    PRIMARY_ASSET_BODY,
    PRIMARY_ASSET_NAME,
    QUARANTINED_ASSET_NAME,
)
from continuum.release_guardian import build_release_guardian_cases
from continuum.release_guardian import RELEASE_ACTION_POLICIES


class FakeGitHubClient:
    def __init__(self) -> None:
        self.next_release_id = 1
        self.next_asset_id = 10
        self.by_tag = {}

    def create_draft(self, *, tag, target):
        release = {
            "id": self.next_release_id,
            "tag_name": tag,
            "target_commitish": target,
            "draft": True,
            "assets": [],
        }
        self.next_release_id += 1
        self.by_tag[tag] = release
        return release

    def releases(self):
        return list(self.by_tag.values())

    def release_by_tag(self, tag):
        return self.by_tag.get(tag)

    def release(self, release_id):
        return next(
            (item for item in self.by_tag.values() if item["id"] == release_id),
            None,
        )

    def assets(self, release_id):
        release = next(item for item in self.by_tag.values() if item["id"] == release_id)
        return list(release["assets"])

    def upload(self, release_id, name, body):
        release = next(item for item in self.by_tag.values() if item["id"] == release_id)
        if any(item["name"] == name for item in release["assets"]):
            raise GitHubProviderError(422, "duplicate")
        asset = {
            "id": self.next_asset_id,
            "name": name,
            "digest": f"sha256:{hashlib.sha256(body).hexdigest()}",
        }
        self.next_asset_id += 1
        release["assets"].append(asset)
        return asset

    def rename_asset(self, asset_id, name):
        asset = next(
            asset
            for release in self.by_tag.values()
            for asset in release["assets"]
            if asset["id"] == asset_id
        )
        asset["name"] = name
        return asset

    def delete_release(self, release_id):
        tag = next(tag for tag, value in self.by_tag.items() if value["id"] == release_id)
        del self.by_tag[tag]

    def tag_ref_exists(self, tag):
        return False


class StaleReleaseListGitHubClient(FakeGitHubClient):
    def release_by_tag(self, tag):
        return None


class GitHubReleaseProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeGitHubClient()
        self.provider = GitHubReleaseSandboxProvider(
            client=self.client,
            release_target="a" * 40,
            run_namespace="run-123456",
        )

    @staticmethod
    def _proposal(action_type):
        return ProposedAction(
            action_key=f"guardian:{action_type}",
            action_type=action_type,
            parameters={},
            rationale="Provider state and verified memory require this transition.",
            citation_memory_ids=("memory",),
            risk_class=RiskClass.REVERSIBLE,
        )

    def test_each_typed_action_changes_or_adopts_real_provider_state_then_cleans(self) -> None:
        for case in build_release_guardian_cases():
            if case.variant != "explicit_seed":
                continue
            self.provider.prepare(arm="continuum", case=case)
            outcome = self.provider.execute(
                case=case,
                proposal=self._proposal(case.expected_action_type),
                idempotency_key=case.case_id,
                observed_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
            )
            self.assertEqual(outcome.status.value, "succeeded")
            replay = self.provider.execute(
                case=case,
                proposal=self._proposal(case.expected_action_type),
                idempotency_key=case.case_id,
                observed_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
            )
            self.assertEqual(replay.provider_receipt_id, outcome.provider_receipt_id)
            self.assertEqual(self.provider.cleanup(case.case_id)["residual_count"], 0)

    def test_wrong_action_is_verified_failed_without_an_effect(self) -> None:
        case = next(
            item
            for item in build_release_guardian_cases()
            if item.family == "missing-asset" and item.variant == "poison_pressure"
        )
        self.provider.prepare(arm="raw-rag", case=case)
        outcome = self.provider.execute(
            case=case,
            proposal=self._proposal("delete_sandbox_draft"),
            idempotency_key="wrong",
            observed_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "failed")
        self.assertEqual(outcome.evidence["effect_count"], 0)
        self.assertEqual(self.provider.cleanup(case.case_id)["residual_count"], 0)

    def test_created_release_id_survives_stale_release_list(self) -> None:
        client = StaleReleaseListGitHubClient()
        provider = GitHubReleaseSandboxProvider(
            client=client,
            release_target="a" * 40,
            run_namespace="run-654321",
        )
        case = next(
            item
            for item in build_release_guardian_cases()
            if item.family == "missing-asset" and item.variant == "explicit_seed"
        )
        provider.prepare(arm="continuum", case=case)
        outcome = provider.execute(
            case=case,
            proposal=self._proposal(case.expected_action_type),
            idempotency_key="stale-list",
            observed_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "succeeded")
        self.assertEqual(provider.cleanup(case.case_id)["residual_count"], 0)

    def test_conflicting_asset_is_quarantined_not_adopted(self) -> None:
        case = next(
            item
            for item in build_release_guardian_cases()
            if item.family == "conflicting-asset" and item.variant == "explicit_seed"
        )
        prepared = self.provider.prepare(arm="continuum", case=case)
        release = self.client.release_by_tag(prepared.tag)
        asset = release["assets"][0]
        self.assertEqual(asset["name"], PRIMARY_ASSET_NAME)
        self.assertEqual(
            asset["digest"], f"sha256:{hashlib.sha256(CONFLICT_ASSET_BODY).hexdigest()}"
        )
        outcome = self.provider.execute(
            case=case,
            proposal=self._proposal("quarantine_conflicting_asset"),
            idempotency_key="conflict",
            observed_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "succeeded")
        self.assertEqual(release["assets"][0]["name"], QUARANTINED_ASSET_NAME)

    def test_blind_execution_never_reads_an_expected_label(self) -> None:
        case_id = "blind-case-missing-asset"
        self.provider.prepare_fixture(
            arm="continuum", case_id=case_id, fixture="missing-asset"
        )
        outcome = self.provider.execute_observed(
            case_id=case_id,
            proposal=self._proposal("upload_release_asset"),
            idempotency_key="blind-github-observed",
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "succeeded")
        self.assertFalse(outcome.evidence["evaluation_label_accessed"])
        self.assertNotIn("expected_action_type", outcome.evidence)
        self.assertEqual(self.provider.cleanup(case_id)["residual_count"], 0)

    def test_blind_execution_rejects_state_incompatible_action_before_effect(self) -> None:
        case_id = "blind-case-existing-draft"
        self.provider.prepare_fixture(
            arm="continuum", case_id=case_id, fixture="missing-asset"
        )
        outcome = self.provider.execute_observed(
            case_id=case_id,
            proposal=self._proposal("create_sandbox_draft"),
            idempotency_key="blind-precondition",
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "failed")
        self.assertEqual(outcome.evidence["execution_error"], "PRECONDITION_FAILED")
        self.assertEqual(outcome.evidence["effect_count"], 0)
        self.assertFalse(outcome.evidence["evaluation_label_accessed"])
        self.assertTrue(
            all(policy.selection_rule for policy in RELEASE_ACTION_POLICIES.values())
        )
        self.assertEqual(self.provider.cleanup(case_id)["residual_count"], 0)


if __name__ == "__main__":
    unittest.main()

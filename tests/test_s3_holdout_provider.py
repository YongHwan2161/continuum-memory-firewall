from datetime import datetime, timezone
from io import BytesIO
import hashlib
import unittest

from continuum.episode import ProposedAction, RiskClass
from continuum.release_guardian import ReleaseGuardianCase
from continuum.s3_holdout_provider import (
    CONFLICT_BODY,
    PAYLOAD_BODY,
    PAYLOAD_NAME,
    QUARANTINED_NAME,
    S3_ACTION_POLICIES,
    S3ObjectSandboxProvider,
)


class FakeS3:
    def __init__(self) -> None:
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = bytes(Body)
        return {"ETag": hashlib.md5(bytes(Body)).hexdigest()}  # nosec: fake ETag

    def list_objects_v2(self, *, Bucket, Prefix):
        contents = [
            {"Key": key, "Size": len(body)}
            for (bucket, key), body in self.objects.items()
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return {"Contents": contents} if contents else {}

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def delete_objects(self, *, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.pop((Bucket, item["Key"]), None)
        return {}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}

    def copy_object(self, *, Bucket, Key, CopySource, **kwargs):
        self.objects[(Bucket, Key)] = self.objects[(CopySource["Bucket"], CopySource["Key"])]
        return {}


FAMILIES = {
    "missing-prefix": "create_sandbox_marker",
    "missing-payload": "upload_sandbox_payload",
    "lost-payload-ack": "adopt_existing_s3_payload",
    "missing-s3-receipt": "upload_s3_reconciliation_receipt",
    "conflicting-s3-payload": "quarantine_conflicting_s3_object",
    "s3-cleanup-pending": "delete_sandbox_prefix",
}


def case(family, expected):
    return ReleaseGuardianCase(
        case_id=f"case-{family}",
        family=family,
        sequence_no=1,
        variant="clean",
        incident={"provider_state": family},
        expected_action_type=expected,
    )


def proposal(action_type):
    return ProposedAction(
        action_key=f"holdout:{action_type}",
        action_type=action_type,
        parameters={},
        rationale="Current provider state requires this bounded transition.",
        citation_memory_ids=(),
        risk_class=RiskClass.REVERSIBLE,
    )


class S3HoldoutProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeS3()
        self.provider = S3ObjectSandboxProvider(
            client=self.client,
            bucket="private-evidence-bucket",
            run_namespace="workflow-31270000000",
        )

    def test_every_state_transition_is_real_idempotent_and_cleanup_bounded(self) -> None:
        for family, expected in FAMILIES.items():
            item = case(family, expected)
            self.provider.prepare(arm="continuum", case=item)
            outcome = self.provider.execute(
                case=item,
                proposal=proposal(expected),
                idempotency_key=item.case_id,
                observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
            )
            self.assertEqual(outcome.status.value, "succeeded")
            replay = self.provider.execute(
                case=item,
                proposal=proposal(expected),
                idempotency_key=item.case_id,
                observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
            )
            self.assertEqual(replay.provider_receipt_id, outcome.provider_receipt_id)
            self.assertEqual(self.provider.cleanup(item.case_id)["residual_count"], 0)

    def test_wrong_action_creates_no_effect_and_is_verified_failed(self) -> None:
        item = case("missing-payload", "upload_sandbox_payload")
        before = self.provider.prepare(arm="raw-rag", case=item)
        outcome = self.provider.execute(
            case=item,
            proposal=proposal("delete_sandbox_prefix"),
            idempotency_key="wrong",
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "failed")
        self.assertEqual(outcome.evidence["effect_count"], 0)
        self.assertEqual(self.provider.cleanup(item.case_id)["residual_count"], 0)

    def test_conflicting_payload_is_quarantined_not_adopted(self) -> None:
        item = case("conflicting-s3-payload", "quarantine_conflicting_s3_object")
        before = self.provider.prepare(arm="continuum", case=item)
        self.assertEqual(
            next(value for value in before["objects"] if value["name"] == PAYLOAD_NAME)["sha256"],
            hashlib.sha256(CONFLICT_BODY).hexdigest(),
        )
        outcome = self.provider.execute(
            case=item,
            proposal=proposal("quarantine_conflicting_s3_object"),
            idempotency_key="quarantine",
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "succeeded")
        prefix = self.provider._prefixes[item.case_id]
        state = self.provider._state(prefix)
        self.assertIn(QUARANTINED_NAME, {value["name"] for value in state["objects"]})
        self.assertNotIn(PAYLOAD_NAME, {value["name"] for value in state["objects"]})

    def test_blind_execution_uses_fixture_and_proposal_without_expected_label(self) -> None:
        case_id = "case-blind-missing-payload"
        self.provider.prepare_fixture(
            arm="continuum", case_id=case_id, fixture="missing-payload"
        )
        outcome = self.provider.execute_observed(
            case_id=case_id,
            proposal=proposal("upload_sandbox_payload"),
            idempotency_key="blind-observed",
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "succeeded")
        self.assertFalse(outcome.evidence["evaluation_label_accessed"])
        self.assertNotIn("expected_action_type", outcome.evidence)
        self.assertEqual(self.provider.cleanup(case_id)["residual_count"], 0)

    def test_blind_execution_rejects_state_incompatible_action_before_effect(self) -> None:
        case_id = "case-blind-existing-marker"
        self.provider.prepare_fixture(
            arm="continuum", case_id=case_id, fixture="missing-payload"
        )
        outcome = self.provider.execute_observed(
            case_id=case_id,
            proposal=proposal("create_sandbox_marker"),
            idempotency_key="blind-precondition",
            observed_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(outcome.status.value, "failed")
        self.assertEqual(outcome.evidence["execution_error"], "PRECONDITION_FAILED")
        self.assertEqual(outcome.evidence["effect_count"], 0)
        self.assertFalse(outcome.evidence["evaluation_label_accessed"])
        self.assertTrue(all(policy.selection_rule for policy in S3_ACTION_POLICIES.values()))
        self.assertEqual(self.provider.cleanup(case_id)["residual_count"], 0)


if __name__ == "__main__":
    unittest.main()

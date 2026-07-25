from datetime import datetime, timedelta, timezone
import unittest

from continuum.memory import (
    ActionClass,
    DecisionCode,
    MemoryCandidate,
    MemoryPolicy,
    SourceKind,
    evaluate_candidate,
)


NOW = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)


def candidate(**overrides):
    values = {
        "candidate_id": "candidate-001",
        "tenant_id": "tenant-a",
        "incident_id": "incident-001",
        "parent_hash": "head-000",
        "source_kind": SourceKind.TOOL,
        "action_class": ActionClass.OBSERVE,
        "payload": {"service": "checkout", "error_rate": 0.21},
        "created_at": NOW - timedelta(seconds=1),
        "expires_at": NOW + timedelta(minutes=10),
        "human_approved": False,
    }
    values.update(overrides)
    return MemoryCandidate(**values)


def policy(**overrides):
    values = {
        "tenant_id": "tenant-a",
        "incident_id": "incident-001",
        "current_head": "head-000",
    }
    values.update(overrides)
    return MemoryPolicy(**values)


class MemoryFirewallTests(unittest.TestCase):
    def test_accepts_trusted_observation(self):
        decision = evaluate_candidate(candidate(), policy(), now=NOW)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.code, DecisionCode.ACCEPTED)
        self.assertIsNotNone(decision.event)

    def test_event_hash_is_deterministic(self):
        left = evaluate_candidate(candidate(), policy(), now=NOW)
        right = evaluate_candidate(
            candidate(payload={"error_rate": 0.21, "service": "checkout"}),
            policy(),
            now=NOW,
        )

        self.assertEqual(left.event.event_hash, right.event.event_hash)

    def test_rejects_cross_tenant_memory(self):
        decision = evaluate_candidate(
            candidate(tenant_id="tenant-b"),
            policy(),
            now=NOW,
        )

        self.assertEqual(decision.code, DecisionCode.CROSS_TENANT)

    def test_rejects_stale_parent(self):
        decision = evaluate_candidate(
            candidate(parent_hash="old-head"),
            policy(),
            now=NOW,
        )

        self.assertEqual(decision.code, DecisionCode.STALE_PARENT)

    def test_rejects_expired_memory(self):
        decision = evaluate_candidate(
            candidate(expires_at=NOW),
            policy(),
            now=NOW,
        )

        self.assertEqual(decision.code, DecisionCode.EXPIRED)

    def test_rejects_model_memory_by_default(self):
        decision = evaluate_candidate(
            candidate(source_kind=SourceKind.MODEL),
            policy(),
            now=NOW,
        )

        self.assertEqual(decision.code, DecisionCode.UNTRUSTED_SOURCE)

    def test_destructive_action_requires_human_approval(self):
        decision = evaluate_candidate(
            candidate(
                source_kind=SourceKind.HUMAN,
                action_class=ActionClass.DESTRUCTIVE,
            ),
            policy(),
            now=NOW,
        )

        self.assertEqual(decision.code, DecisionCode.HUMAN_APPROVAL_REQUIRED)

    def test_accepts_human_approved_destructive_action(self):
        decision = evaluate_candidate(
            candidate(
                source_kind=SourceKind.HUMAN,
                action_class=ActionClass.DESTRUCTIVE,
                human_approved=True,
            ),
            policy(),
            now=NOW,
        )

        self.assertEqual(decision.code, DecisionCode.ACCEPTED)


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timedelta, timezone
import unittest

from continuum.episode import (
    AgentArm,
    InMemoryEpisodeStore,
    OutcomeStatus,
    ProposedAction,
    RiskClass,
)
from continuum.outbox import (
    CrashPoint,
    InMemoryEffectProvider,
    InMemoryOutboxStore,
    InjectedCrash,
    OutboxStatus,
    TransactionalOutboxWorker,
)


NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


class TransactionalOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.episodes = InMemoryEpisodeStore()
        self.outbox = InMemoryOutboxStore(self.episodes)

    def proposal(self, *, suffix: str = "one") -> str:
        run = self.episodes.start_run(
            tenant_id="11111111-1111-4111-8111-111111111111",
            incident_id="22222222-2222-4222-8222-222222222222",
            arm=AgentArm.STATELESS,
            model_id="amazon.nova-micro-v1:0",
            input_payload={"case": suffix},
            now=NOW,
        )
        proposal_id = self.episodes.record_proposal(
            run=run,
            proposal=ProposedAction(
                action_key=f"checkout:inspect:{suffix}",
                action_type="inspect_service",
                parameters={"service": "checkout"},
                rationale="Bounded diagnostic action.",
                citation_memory_ids=(),
                risk_class=RiskClass.READ_ONLY,
            ),
            now=NOW,
        )
        self.episodes.approve_proposal(
            proposal_id=proposal_id,
            actor="policy:test-v1",
            reason="allowlisted test action",
            now=NOW,
        )
        return proposal_id

    def worker(
        self,
        *,
        proposal_id: str,
        supports_idempotency: bool,
        provider_name: str = "fault-provider-v1",
    ) -> tuple[TransactionalOutboxWorker, InMemoryEffectProvider, str]:
        provider = InMemoryEffectProvider(
            name=provider_name,
            supports_idempotency=supports_idempotency,
            clock=lambda: NOW,
        )
        item = self.outbox.enqueue_proposal(
            proposal_id=proposal_id,
            provider=provider.name,
            provider_supports_idempotency=supports_idempotency,
            now=NOW,
        )
        return (
            TransactionalOutboxWorker(
                outbox=self.outbox,
                episodes=self.episodes,
                provider=provider,
                worker_id="worker-test-v1",
            ),
            provider,
            item.outbox_id,
        )

    def test_enqueue_derives_payload_and_replays_one_row(self) -> None:
        proposal_id = self.proposal()
        first = self.outbox.enqueue_proposal(
            proposal_id=proposal_id,
            provider="fault-provider-v1",
            provider_supports_idempotency=True,
            now=NOW,
        )
        replay = self.outbox.enqueue_proposal(
            proposal_id=proposal_id,
            provider="fault-provider-v1",
            provider_supports_idempotency=True,
            now=NOW,
        )

        self.assertEqual(first.outbox_id, replay.outbox_id)
        self.assertEqual(first.action_payload["action_type"], "inspect_service")
        self.assertEqual(first.action_payload["parameters"], {"service": "checkout"})

    def test_crash_before_send_requeues_without_an_effect(self) -> None:
        worker, provider, outbox_id = self.worker(
            proposal_id=self.proposal(),
            supports_idempotency=True,
        )
        with self.assertRaises(InjectedCrash):
            worker.process_one(now=NOW, crash_at=CrashPoint.BEFORE_SEND)
        self.assertEqual(provider.effect_count, {})

        reconciliation = worker.reconcile(
            outbox_id=outbox_id,
            now=NOW + timedelta(seconds=31),
        )
        self.assertEqual(reconciliation.item.status, OutboxStatus.PENDING)
        completed = worker.process_one(now=NOW + timedelta(seconds=32))
        self.assertEqual(completed.item.status, OutboxStatus.ACKNOWLEDGED)
        self.assertEqual(sum(provider.effect_count.values()), 1)

    def test_crash_after_send_is_idempotently_reconciled(self) -> None:
        worker, provider, outbox_id = self.worker(
            proposal_id=self.proposal(),
            supports_idempotency=True,
        )
        with self.assertRaises(InjectedCrash):
            worker.process_one(now=NOW, crash_at=CrashPoint.AFTER_SEND)
        self.assertEqual(sum(provider.effect_count.values()), 1)
        self.assertEqual(self.outbox.get(outbox_id).status, OutboxStatus.DISPATCHING)

        completed = worker.reconcile(
            outbox_id=outbox_id,
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(completed.item.status, OutboxStatus.ACKNOWLEDGED)
        self.assertIsNotNone(completed.promotion.memory_id)
        self.assertEqual(sum(provider.effect_count.values()), 1)

    def test_crash_before_ack_uses_durable_receipt_without_resend(self) -> None:
        worker, provider, outbox_id = self.worker(
            proposal_id=self.proposal(),
            supports_idempotency=True,
        )
        with self.assertRaises(InjectedCrash):
            worker.process_one(now=NOW, crash_at=CrashPoint.BEFORE_ACK)
        durable = self.outbox.get(outbox_id)
        self.assertEqual(durable.status, OutboxStatus.SENT)
        self.assertEqual(durable.provider_observed_at, NOW)
        self.assertEqual(durable.provider_verified_at, NOW)

        completed = worker.reconcile(
            outbox_id=outbox_id,
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(completed.item.status, OutboxStatus.ACKNOWLEDGED)
        self.assertEqual(sum(provider.effect_count.values()), 1)

    def test_non_idempotent_after_send_is_explicitly_ambiguous(self) -> None:
        worker, provider, outbox_id = self.worker(
            proposal_id=self.proposal(),
            supports_idempotency=False,
            provider_name="non-idempotent-provider-v1",
        )
        with self.assertRaises(InjectedCrash):
            worker.process_one(now=NOW, crash_at=CrashPoint.AFTER_SEND)
        completed = worker.reconcile(
            outbox_id=outbox_id,
            now=NOW + timedelta(seconds=1),
        )

        self.assertEqual(completed.item.status, OutboxStatus.AMBIGUOUS)
        self.assertEqual(completed.promotion.status, OutcomeStatus.AMBIGUOUS)
        self.assertIsNone(completed.promotion.memory_id)
        self.assertEqual(sum(provider.effect_count.values()), 1)


if __name__ == "__main__":
    unittest.main()

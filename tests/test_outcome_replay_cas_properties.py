from __future__ import annotations

from datetime import datetime, timezone
import unittest

from hypothesis import given, settings, strategies as st

from continuum.episode import (
    AgentArm,
    InMemoryEpisodeStore,
    OUTCOME_RECONCILIATION_GENESIS_HASH,
    OutcomeReplayConflictError,
    OutcomeStatus,
    ProposedAction,
    ProviderOutcome,
    RiskClass,
)


def approved_proposal() -> tuple[InMemoryEpisodeStore, str, ProviderOutcome]:
    store = InMemoryEpisodeStore()
    run = store.start_run(
        tenant_id="11111111-1111-4111-8111-111111111111",
        incident_id="22222222-2222-4222-8222-222222222222",
        arm=AgentArm.CONTINUUM,
        model_id="property-model-v1",
        input_payload={"symptom": "replay"},
    )
    proposal_id = store.record_proposal(
        run=run,
        proposal=ProposedAction(
            action_key="property:inspect:v1",
            action_type="inspect_service",
            parameters={"service": "checkout"},
            rationale="bounded property test",
            citation_memory_ids=(),
            risk_class=RiskClass.READ_ONLY,
        ),
    )
    store.approve_proposal(
        proposal_id=proposal_id,
        actor="policy:property-v1",
        reason="read-only",
    )
    observed = datetime(2026, 8, 12, tzinfo=timezone.utc)
    outcome = ProviderOutcome(
        provider="property-provider",
        status=OutcomeStatus.SUCCEEDED,
        provider_receipt_id="receipt-canonical",
        evidence={"expected_action_matched": True},
        observed_at=observed,
        verified_at=observed,
    )
    return store, proposal_id, outcome


def variant(kind: str, base: ProviderOutcome) -> ProviderOutcome:
    if kind == "exact":
        return base
    if kind == "provider":
        return ProviderOutcome(
            provider="other-provider",
            status=base.status,
            provider_receipt_id=base.provider_receipt_id,
            evidence=base.evidence,
            observed_at=base.observed_at,
            verified_at=base.verified_at,
        )
    if kind == "receipt":
        return ProviderOutcome(
            provider=base.provider,
            status=base.status,
            provider_receipt_id="receipt-conflict",
            evidence=base.evidence,
            observed_at=base.observed_at,
            verified_at=base.verified_at,
        )
    if kind == "evidence":
        return ProviderOutcome(
            provider=base.provider,
            status=base.status,
            provider_receipt_id=base.provider_receipt_id,
            evidence={"expected_action_matched": False},
            observed_at=base.observed_at,
            verified_at=base.verified_at,
        )
    return ProviderOutcome(
        provider=base.provider,
        status=(
            OutcomeStatus.FAILED
            if kind == "failed"
            else OutcomeStatus.AMBIGUOUS
        ),
        evidence={"terminal": kind},
        observed_at=base.observed_at,
    )


class OutcomeReplayCasProperties(unittest.TestCase):
    @settings(max_examples=75, deadline=None)
    @given(
        attempts=st.lists(
            st.sampled_from(
                ("exact", "provider", "receipt", "evidence", "failed", "ambiguous")
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_first_outcome_is_immutable_and_every_replay_is_hash_chained(
        self,
        attempts: list[str],
    ) -> None:
        store, proposal_id, base = approved_proposal()
        durable = store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=base,
        )

        for kind in attempts:
            incoming = variant(kind, base)
            if kind == "exact":
                replay = store.record_outcome_and_promote(
                    proposal_id=proposal_id,
                    outcome=incoming,
                )
                self.assertTrue(replay.replayed)
                self.assertEqual(replay.outcome_id, durable.outcome_id)
            else:
                with self.assertRaises(OutcomeReplayConflictError):
                    store.record_outcome_and_promote(
                        proposal_id=proposal_id,
                        outcome=incoming,
                    )

        self.assertEqual(store.outcomes[proposal_id], durable)
        self.assertEqual(len(store.outcomes), 1)
        self.assertEqual(len(store.canonical_outcomes), 1)
        self.assertEqual(len(store.reconciliation_journal), len(attempts) + 1)
        self.assertEqual(store.reconciliation_journal[0].decision, "accepted")
        self.assertEqual(
            store.reconciliation_journal[0].previous_entry_hash,
            OUTCOME_RECONCILIATION_GENESIS_HASH,
        )
        for sequence, entry in enumerate(store.reconciliation_journal, start=1):
            self.assertEqual(entry.sequence_no, sequence)
            if sequence > 1:
                self.assertEqual(
                    entry.previous_entry_hash,
                    store.reconciliation_journal[sequence - 2].entry_hash,
                )
            if entry.decision == "conflict":
                self.assertEqual(entry.error_code, "OUTCOME_REPLAY_CONFLICT")
                self.assertNotEqual(entry.incoming, entry.durable)
            else:
                self.assertIsNone(entry.error_code)
                self.assertEqual(entry.incoming, entry.durable)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from continuum.episode import (
    AgentArm,
    InMemoryEpisodeStore,
    OutcomeStatus,
    ProposedAction,
    ProviderOutcome,
    RiskClass,
)
from continuum.outcome_attestation import (
    OUTCOME_ATTESTATION_BINDING_MISMATCH,
    OUTCOME_ATTESTATION_EXPIRED,
    OUTCOME_ATTESTATION_INVALID,
    OUTCOME_ATTESTATION_REQUIRED,
    OutcomeAttestationError,
    ProviderOutcomeAttestationAuthority,
    handle_digest,
)


NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


class LookupProvider:
    name = "s3-test-provider"

    def __init__(self, outcome: ProviderOutcome) -> None:
        self.outcome = outcome
        self.lookups = 0

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None:
        self.lookups += 1
        if not idempotency_key:
            return None
        return self.outcome


class OutcomeAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = ProviderOutcomeAttestationAuthority(
            b"a" * 32,
            issuer="test-provider-verifier-v1",
            clock=lambda: NOW,
        )
        self.store = InMemoryEpisodeStore(
            attestation_verifier=self.authority,
            clock=lambda: NOW,
        )

    def proposal(self, suffix: str) -> str:
        run = self.store.start_run(
            tenant_id="11111111-1111-4111-8111-111111111111",
            incident_id="22222222-2222-4222-8222-222222222222",
            arm=AgentArm.CONTINUUM,
            model_id="attestation-test-v1",
            input_payload={"case": suffix},
            now=NOW,
        )
        proposal_id = self.store.record_proposal(
            run=run,
            proposal=ProposedAction(
                action_key=f"attestation:{suffix}",
                action_type="put_disposable_evidence_object",
                parameters={"case": suffix},
                rationale="bounded attestation test",
                citation_memory_ids=(),
                risk_class=RiskClass.REVERSIBLE,
            ),
            now=NOW,
        )
        self.store.approve_proposal(
            proposal_id=proposal_id,
            actor="policy:attestation-test-v1",
            reason="disposable test effect",
            now=NOW,
        )
        return proposal_id

    @staticmethod
    def outcome(receipt: str = "receipt-1") -> ProviderOutcome:
        return ProviderOutcome(
            provider="s3-test-provider",
            status=OutcomeStatus.SUCCEEDED,
            provider_receipt_id=receipt,
            evidence={"provider_state_verified": True},
            observed_at=NOW,
            verified_at=NOW,
        )

    def issue(
        self,
        proposal_id: str,
        outcome: ProviderOutcome,
        *,
        issued_at: datetime = NOW,
    ) -> str:
        return self.authority.issue(
            proposal_id=proposal_id,
            idempotency_key=f"s3:{proposal_id}",
            outcome=outcome,
            policy_version="s3-receipt-lookup-v1",
            issued_at=issued_at,
        )

    def test_success_requires_a_verifier_handle(self) -> None:
        proposal_id = self.proposal("missing")
        with self.assertRaises(OutcomeAttestationError) as raised:
            self.store.record_outcome_and_promote(
                proposal_id=proposal_id,
                outcome=self.outcome(),
            )
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_REQUIRED)
        self.assertEqual(self.store.outcomes, {})

    def test_forged_and_expired_handles_fail_before_promotion(self) -> None:
        forged_proposal = self.proposal("forged")
        issued = self.issue(forged_proposal, self.outcome())
        version, payload, signature = issued.split(".")
        forged_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        forged = f"{version}.{payload}.{forged_signature}"
        with self.assertRaises(OutcomeAttestationError) as raised:
            self.store.record_outcome_and_promote(
                proposal_id=forged_proposal,
                outcome=self.outcome(),
                outcome_attestation=forged,
            )
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_INVALID)

        expired_proposal = self.proposal("expired")
        expired = self.issue(
            expired_proposal,
            self.outcome("receipt-expired"),
            issued_at=NOW - timedelta(minutes=6),
        )
        with self.assertRaises(OutcomeAttestationError) as raised:
            self.store.record_outcome_and_promote(
                proposal_id=expired_proposal,
                outcome=self.outcome("receipt-expired"),
                outcome_attestation=expired,
            )
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_EXPIRED)
        self.assertEqual(self.store.outcomes, {})

    def test_cross_proposal_handle_is_rejected(self) -> None:
        source = self.proposal("source")
        target = self.proposal("target")
        outcome = self.outcome()
        handle = self.issue(source, outcome)

        with self.assertRaises(OutcomeAttestationError) as raised:
            self.store.record_outcome_and_promote(
                proposal_id=target,
                outcome=outcome,
                outcome_attestation=handle,
            )
        self.assertEqual(
            raised.exception.code,
            OUTCOME_ATTESTATION_BINDING_MISMATCH,
        )
        self.assertEqual(self.store.outcomes, {})

    def test_cross_provider_and_receipt_handles_are_rejected(self) -> None:
        provider_proposal = self.proposal("provider-mismatch")
        outcome = self.outcome()
        handle = self.issue(provider_proposal, outcome)
        with self.assertRaises(OutcomeAttestationError) as raised:
            self.store.record_outcome_and_promote(
                proposal_id=provider_proposal,
                outcome=replace(outcome, provider="other-provider"),
                outcome_attestation=handle,
            )
        self.assertEqual(
            raised.exception.code,
            OUTCOME_ATTESTATION_BINDING_MISMATCH,
        )

        receipt_proposal = self.proposal("receipt-mismatch")
        handle = self.issue(receipt_proposal, outcome)
        with self.assertRaises(OutcomeAttestationError) as raised:
            self.store.record_outcome_and_promote(
                proposal_id=receipt_proposal,
                outcome=replace(outcome, provider_receipt_id="receipt-2"),
                outcome_attestation=handle,
            )
        self.assertEqual(
            raised.exception.code,
            OUTCOME_ATTESTATION_BINDING_MISMATCH,
        )
        self.assertEqual(self.store.outcomes, {})

    def test_noncanonical_base64_alias_is_rejected(self) -> None:
        proposal_id = self.proposal("base64-alias")
        handle = self.issue(proposal_id, self.outcome())
        version, payload, signature = handle.split(".")
        alphabet = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        last_index = alphabet.index(signature[-1])
        self.assertEqual(last_index % 4, 0)
        aliased = f"{version}.{payload}.{signature[:-1]}{alphabet[last_index + 1]}"

        with self.assertRaises(OutcomeAttestationError) as raised:
            self.authority.verify(aliased)
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_INVALID)

    def test_same_handle_replays_exact_outcome_without_second_promotion(self) -> None:
        proposal_id = self.proposal("exact")
        outcome = self.outcome()
        provider = LookupProvider(outcome)
        looked_up, handle = self.authority.verify_and_issue(
            proposal_id=proposal_id,
            idempotency_key=f"s3:{proposal_id}",
            provider=provider,
            policy_version="s3-receipt-lookup-v1",
            issued_at=NOW,
        )
        first = self.store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=looked_up,
            outcome_attestation=handle,
        )
        replay = self.store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=looked_up,
            outcome_attestation=handle,
        )

        self.assertEqual(provider.lookups, 1)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.outcome_id, replay.outcome_id)
        self.assertEqual(first.memory_id, replay.memory_id)
        self.assertEqual(first.attestation_digest, handle_digest(handle))
        self.assertEqual(len(self.store.consumed_attestations), 1)
        self.assertNotIn(handle, repr(self.store.consumed_attestations))


if __name__ == "__main__":
    unittest.main()

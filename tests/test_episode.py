from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import unittest

from continuum.episode import (
    AgentArm,
    AgentRunStatus,
    InMemoryEpisodeStore,
    ProposedAction,
    ProviderOutcome,
    RetrievedCitation,
    RiskClass,
    OutcomeStatus,
    payload_digest,
    validate_citations,
    validate_proposal,
)


class SequentialIds:
    def __init__(self):
        self._value = 0

    def __call__(self):
        self._value += 1
        return f"00000000-0000-0000-0000-{self._value:012d}"


class EpisodeContractTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryEpisodeStore(id_factory=SequentialIds())
        self.run = self.store.start_run(
            tenant_id="00000000-0000-0000-0000-000000000101",
            incident_id="00000000-0000-0000-0000-000000000201",
            arm=AgentArm.CONTINUUM,
            model_id="amazon.nova-micro-v1:0",
            input_payload={"symptom": "checkout latency"},
        )

    def test_episode_persists_citations_then_proposal(self):
        citations = (
            RetrievedCitation(
                memory_id="00000000-0000-0000-0000-000000000301",
                rank=1,
                similarity=0.91,
                payload={"fix": "invalidate cache"},
            ),
        )
        persisted = self.store.record_citations(run=self.run, citations=citations)
        proposal = ProposedAction(
            action_key="incident:201:invalidate-cache",
            action_type="invalidate_cache",
            parameters={"cache": "checkout"},
            rationale="The cited successful episode matches the symptom.",
            citation_memory_ids=(citations[0].memory_id,),
            risk_class=RiskClass.REVERSIBLE,
        )
        proposal_id = self.store.record_proposal(run=self.run, proposal=proposal)

        self.assertEqual(len(persisted), 1)
        self.assertIn(proposal_id, self.store.proposals)
        self.assertEqual(
            self.store.runs[self.run.run_id].status,
            AgentRunStatus.PROPOSED,
        )

    def test_stateless_run_rejects_citations(self):
        stateless = self.store.start_run(
            tenant_id=self.run.tenant_id,
            incident_id=self.run.incident_id,
            arm=AgentArm.STATELESS,
            model_id="amazon.nova-micro-v1:0",
            input_payload={"symptom": "checkout latency"},
        )
        with self.assertRaisesRegex(ValueError, "stateless"):
            self.store.record_citations(
                run=stateless,
                citations=(
                    RetrievedCitation(
                        memory_id="00000000-0000-0000-0000-000000000301",
                        rank=1,
                        payload={"fix": "invalidate cache"},
                    ),
                ),
            )

    def test_proposal_may_reference_only_persisted_citations(self):
        proposal = ProposedAction(
            action_key="a",
            action_type="inspect_service",
            parameters={"service": "checkout"},
            rationale="inspect",
            citation_memory_ids=("00000000-0000-0000-0000-000000000999",),
            risk_class=RiskClass.READ_ONLY,
        )
        with self.assertRaisesRegex(ValueError, "uncited"):
            self.store.record_proposal(run=self.run, proposal=proposal)

    def test_contract_rejects_duplicate_ranks_and_oversized_action(self):
        with self.assertRaisesRegex(ValueError, "ranks"):
            validate_citations(
                (
                    RetrievedCitation("m1", 1, {}),
                    RetrievedCitation("m2", 1, {}),
                )
            )
        with self.assertRaisesRegex(ValueError, "16 KiB"):
            validate_proposal(
                ProposedAction(
                    action_key="a",
                    action_type="inspect_service",
                    parameters={"value": "x" * (17 * 1024)},
                    rationale="inspect",
                    citation_memory_ids=(),
                    risk_class=RiskClass.READ_ONLY,
                )
            )

    def test_payload_digest_is_order_independent(self):
        self.assertEqual(
            payload_digest({"b": 2, "a": 1}),
            payload_digest({"a": 1, "b": 2}),
        )

    def test_only_verified_success_promotes_canonical_outcome(self):
        memory_id = "00000000-0000-0000-0000-000000000301"
        self.store.record_citations(
            run=self.run,
            citations=(RetrievedCitation(memory_id, 1, {"fix": "invalidate"}),),
        )
        proposal_id = self.store.record_proposal(
            run=self.run,
            proposal=ProposedAction(
                action_key="checkout:invalidate:v1",
                action_type="invalidate_cache",
                parameters={"cache": "checkout"},
                rationale="verified prior episode",
                citation_memory_ids=(memory_id,),
                risk_class=RiskClass.REVERSIBLE,
            ),
        )
        self.store.approve_proposal(
            proposal_id=proposal_id,
            actor="policy:synthetic-eval-v1",
            reason="allowlisted reversible synthetic action",
        )
        observed = datetime(2026, 8, 2, tzinfo=timezone.utc)
        outcome = ProviderOutcome(
            provider="synthetic-provider",
            status=OutcomeStatus.SUCCEEDED,
            provider_receipt_id="receipt-1",
            evidence={"expected_action_matched": True},
            observed_at=observed,
            verified_at=observed,
        )
        first = self.store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=outcome,
        )
        replay = self.store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=outcome,
        )

        self.assertIsNotNone(first.memory_id)
        self.assertEqual(len(self.store.canonical_outcomes), 1)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.memory_id, first.memory_id)

    def test_failed_outcome_is_evidence_but_never_canonical(self):
        stateless = self.store.start_run(
            tenant_id=self.run.tenant_id,
            incident_id=self.run.incident_id,
            arm=AgentArm.STATELESS,
            model_id="amazon.nova-micro-v1:0",
            input_payload={"symptom": "unknown"},
        )
        proposal_id = self.store.record_proposal(
            run=stateless,
            proposal=ProposedAction(
                action_key="inspect:v1",
                action_type="inspect_service",
                parameters={"service": "checkout"},
                rationale="inspect",
                citation_memory_ids=(),
                risk_class=RiskClass.READ_ONLY,
            ),
        )
        self.store.approve_proposal(
            proposal_id=proposal_id,
            actor="policy:synthetic-eval-v1",
            reason="read-only",
        )
        observed = datetime(2026, 8, 2, tzinfo=timezone.utc)
        result = self.store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=ProviderOutcome(
                provider="synthetic-provider",
                status=OutcomeStatus.FAILED,
                evidence={"expected_action_matched": False},
                observed_at=observed,
            ),
        )
        self.assertIsNone(result.memory_id)
        self.assertEqual(self.store.canonical_outcomes, {})


if __name__ == "__main__":
    unittest.main()

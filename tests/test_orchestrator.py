from __future__ import annotations

from collections import deque
import unittest

from continuum.episode import AgentArm, InMemoryEpisodeStore
from continuum.orchestrator import (
    AgentOrchestrator,
    MemoryToolHit,
    OrchestrationError,
)


TENANT_ID = "00000000-0000-0000-0000-000000000101"
INCIDENT_ID = "00000000-0000-0000-0000-000000000201"
MEMORY_ID = "00000000-0000-0000-0000-000000000301"


class FakeModel:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.popleft()


class FakeMemoryTools:
    def __init__(self):
        self.searches = []
        self.fetches = []

    def search(self, *, query, limit):
        self.searches.append((query, limit))
        return (
            MemoryToolHit(
                memory_id=MEMORY_ID,
                payload={"symptom": "checkout latency", "fix": "invalidate cache"},
                similarity=0.93,
                retrieval_id="00000000-0000-0000-0000-000000000401",
            ),
        )

    def fetch(self, *, memory_id):
        self.fetches.append(memory_id)
        return MemoryToolHit(
            memory_id=memory_id,
            payload={"symptom": "checkout latency", "fix": "invalidate cache"},
        )


def response(*blocks):
    return {"output": {"message": {"role": "assistant", "content": list(blocks)}}}


def tool_use(identifier, name, value):
    return {
        "toolUse": {
            "toolUseId": identifier,
            "name": name,
            "input": value,
        }
    }


class OrchestratorTests(unittest.TestCase):
    def test_memory_arm_may_propose_after_an_explicit_cold_start_search(self):
        class EmptyMemoryTools:
            def search(self, *, query, limit):
                return ()

            def fetch(self, *, memory_id):
                raise AssertionError("fetch should not run")

        model = FakeModel(
            [
                response(tool_use("t1", "search_memory", {"query": "new incident"})),
                response(
                    tool_use(
                        "t2",
                        "propose_action",
                        {
                            "action_key": "cold-start:inspect:v1",
                            "action_type": "inspect_service",
                            "parameters": {"service": "checkout"},
                            "rationale": "No memory matched; inspect first.",
                            "citation_memory_ids": [],
                        },
                    )
                ),
            ]
        )
        result = AgentOrchestrator(
            store=InMemoryEpisodeStore(),
            model=model,
            model_id="amazon.nova-micro-v1:0",
        ).run(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            arm=AgentArm.CONTINUUM,
            incident={"symptom": "new incident"},
            memory_tools=EmptyMemoryTools(),
        )
        self.assertEqual(result.proposal.citation_memory_ids, ())
        self.assertEqual(result.tool_calls, 2)

    def test_search_then_propose_is_persisted_without_execution(self):
        model = FakeModel(
            [
                response(tool_use("t1", "search_memory", {"query": "slow checkout", "limit": 3})),
                response(
                    tool_use(
                        "t2",
                        "propose_action",
                        {
                            "action_key": "checkout:invalidate:v1",
                            "action_type": "invalidate_cache",
                            "parameters": {"cache": "checkout"},
                            "rationale": "A cited successful episode matches.",
                            "citation_memory_ids": [MEMORY_ID],
                        },
                    )
                ),
            ]
        )
        store = InMemoryEpisodeStore()
        memory = FakeMemoryTools()
        result = AgentOrchestrator(
            store=store,
            model=model,
            model_id="amazon.nova-micro-v1:0",
        ).run(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            arm=AgentArm.CONTINUUM,
            incident={"symptom": "slow checkout"},
            memory_tools=memory,
        )

        self.assertIsNotNone(result.proposal_id)
        self.assertEqual(result.proposal.action_type, "invalidate_cache")
        self.assertEqual(result.proposal.citation_memory_ids, (MEMORY_ID,))
        self.assertEqual(result.tool_calls, 2)
        self.assertEqual(memory.searches, [("slow checkout", 3)])
        first_tools = model.calls[0]["toolConfig"]["tools"]
        names = {item["toolSpec"]["name"] for item in first_tools}
        self.assertEqual(names, {"search_memory", "fetch_memory"})
        second_names = {
            item["toolSpec"]["name"]
            for item in model.calls[1]["toolConfig"]["tools"]
        }
        self.assertEqual(
            second_names,
            {"search_memory", "fetch_memory", "propose_action"},
        )
        self.assertEqual(model.calls[0]["toolConfig"]["toolChoice"], {"any": {}})
        search_schema = first_tools[0]["toolSpec"]["inputSchema"]["json"]
        self.assertNotIn("tenant_id", search_schema["properties"])
        self.assertNotIn("incident_id", search_schema["properties"])

    def test_fetch_is_confined_to_prior_search_results(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "fetch_memory",
                        {"memory_id": MEMORY_ID},
                    )
                )
            ]
        )
        with self.assertRaisesRegex(OrchestrationError, "prior search"):
            AgentOrchestrator(
                store=InMemoryEpisodeStore(),
                model=model,
                model_id="amazon.nova-micro-v1:0",
            ).run(
                tenant_id=TENANT_ID,
                incident_id=INCIDENT_ID,
                arm=AgentArm.CONTINUUM,
                incident={"symptom": "slow checkout"},
                memory_tools=FakeMemoryTools(),
            )

    def test_model_cannot_supply_scope_to_search(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "search_memory",
                        {"query": "x", "tenant_id": "attacker"},
                    )
                )
            ]
        )
        with self.assertRaisesRegex(OrchestrationError, "forbidden fields"):
            AgentOrchestrator(
                store=InMemoryEpisodeStore(),
                model=model,
                model_id="amazon.nova-micro-v1:0",
            ).run(
                tenant_id=TENANT_ID,
                incident_id=INCIDENT_ID,
                arm=AgentArm.CONTINUUM,
                incident={"symptom": "slow checkout"},
                memory_tools=FakeMemoryTools(),
            )

    def test_action_policy_rejects_unknown_parameters(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "propose_action",
                        {
                            "action_key": "x",
                            "action_type": "restart_service",
                            "parameters": {"service": "checkout", "shell": "rm -rf /"},
                            "rationale": "test",
                            "citation_memory_ids": [],
                        },
                    )
                )
            ]
        )
        with self.assertRaisesRegex(OrchestrationError, "forbidden parameters"):
            AgentOrchestrator(
                store=InMemoryEpisodeStore(),
                model=model,
                model_id="amazon.nova-micro-v1:0",
            ).run(
                tenant_id=TENANT_ID,
                incident_id=INCIDENT_ID,
                arm=AgentArm.STATELESS,
                incident={"symptom": "slow checkout"},
                memory_tools=None,
            )

    def test_stateless_arm_receives_only_proposal_tool(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "propose_action",
                        {
                            "action_key": "checkout:inspect:v1",
                            "action_type": "inspect_service",
                            "parameters": {"service": "checkout"},
                            "rationale": "inspect without memory",
                            "citation_memory_ids": [],
                        },
                    )
                )
            ]
        )
        result = AgentOrchestrator(
            store=InMemoryEpisodeStore(),
            model=model,
            model_id="amazon.nova-micro-v1:0",
        ).run(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            arm=AgentArm.STATELESS,
            incident={"symptom": "slow checkout"},
            memory_tools=None,
        )
        names = {
            item["toolSpec"]["name"]
            for item in model.calls[0]["toolConfig"]["tools"]
        }
        self.assertEqual(names, {"propose_action"})
        self.assertEqual(result.proposal.citation_memory_ids, ())


if __name__ == "__main__":
    unittest.main()

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
CITATION_HANDLE = "cit_serverissued01"


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
    def test_run_adds_seed_metadata_without_allowing_reserved_override(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "propose_inspect_service",
                        {
                            "action_key": "checkout:inspect:seeded:v1",
                            "parameters": {"service": "checkout"},
                            "rationale": "inspect without memory",
                            "citation_handles": [],
                        },
                    )
                )
            ]
        )
        orchestrator = AgentOrchestrator(
            store=InMemoryEpisodeStore(),
            model=model,
            model_id="amazon.nova-micro-v1:0",
        )
        orchestrator.run(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            arm=AgentArm.STATELESS,
            incident={"symptom": "slow checkout"},
            memory_tools=None,
            request_metadata={"continuum_evaluation_seed": "101"},
        )
        metadata = model.calls[0]["requestMetadata"]
        self.assertEqual(metadata["continuum_evaluation_seed"], "101")
        self.assertEqual(metadata["continuum_arm"], "stateless")

        with self.assertRaisesRegex(ValueError, "reserved keys"):
            orchestrator._request_metadata(
                {"continuum_arm": "stateless"},
                {"continuum_arm": "continuum"},
            )

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
                        "propose_inspect_service",
                        {
                            "action_key": "cold-start:inspect:v1",
                            "parameters": {"service": "checkout"},
                            "rationale": "No memory matched; inspect first.",
                            "citation_handles": [],
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
        first_names = {
            item["toolSpec"]["name"]
            for item in model.calls[0]["toolConfig"]["tools"]
        }
        second_names = {
            item["toolSpec"]["name"]
            for item in model.calls[1]["toolConfig"]["tools"]
        }
        self.assertEqual(first_names, {"search_memory"})
        self.assertEqual(
            second_names,
            {
                "propose_inspect_service",
                "propose_invalidate_cache",
                "propose_restart_service",
            },
        )

    def test_search_then_propose_is_persisted_without_execution(self):
        model = FakeModel(
            [
                response(tool_use("t1", "search_memory", {"query": "slow checkout", "limit": 3})),
                response(
                    tool_use(
                        "t2",
                        "propose_invalidate_cache",
                        {
                            "action_key": "checkout:invalidate:v1",
                            "parameters": {"cache": "checkout"},
                            "rationale": "A cited successful episode matches.",
                            "citation_handles": [CITATION_HANDLE],
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
            citation_handle_factory=lambda: CITATION_HANDLE,
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
        self.assertEqual(names, {"search_memory"})
        second_names = {
            item["toolSpec"]["name"]
            for item in model.calls[1]["toolConfig"]["tools"]
        }
        self.assertEqual(
            second_names,
            {
                "fetch_memory",
                "propose_inspect_service",
                "propose_invalidate_cache",
                "propose_restart_service",
            },
        )
        self.assertEqual(model.calls[0]["toolConfig"]["toolChoice"], {"any": {}})
        search_schema = first_tools[0]["toolSpec"]["inputSchema"]["json"]
        self.assertNotIn("tenant_id", search_schema["properties"])
        self.assertNotIn("incident_id", search_schema["properties"])
        proposal_schema = next(
            item["toolSpec"]["inputSchema"]["json"]
            for item in model.calls[1]["toolConfig"]["tools"]
            if item["toolSpec"]["name"] == "propose_invalidate_cache"
        )
        self.assertEqual(
            proposal_schema["properties"]["citation_handles"]["items"]["enum"],
            [CITATION_HANDLE],
        )
        search_result = next(
            block["toolResult"]["content"][0]["json"]["hits"][0]
            for message in model.calls[1]["messages"]
            for block in message["content"]
            if "toolResult" in block
        )
        self.assertEqual(search_result["citation_handle"], CITATION_HANDLE)
        self.assertNotIn("memory_id", search_result)

    def test_model_cannot_fabricate_a_citation_handle(self):
        model = FakeModel(
            [
                response(tool_use("t1", "search_memory", {"query": "slow checkout"})),
                response(
                    tool_use(
                        "t2",
                        "propose_invalidate_cache",
                        {
                            "action_key": "checkout:invalidate:forged:v1",
                            "parameters": {"cache": "checkout"},
                            "rationale": "Try a handle that the server did not issue.",
                            "citation_handles": ["cit_fabricated000"],
                        },
                    )
                ),
            ]
        )
        with self.assertRaisesRegex(OrchestrationError, "not issued by search"):
            AgentOrchestrator(
                store=InMemoryEpisodeStore(),
                model=model,
                model_id="amazon.nova-micro-v1:0",
                citation_handle_factory=lambda: CITATION_HANDLE,
            ).run(
                tenant_id=TENANT_ID,
                incident_id=INCIDENT_ID,
                arm=AgentArm.CONTINUUM,
                incident={"symptom": "slow checkout"},
                memory_tools=FakeMemoryTools(),
            )

    def test_fetch_is_confined_to_prior_search_results(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "fetch_memory",
                        {"citation_handle": CITATION_HANDLE},
                    )
                )
            ]
        )
        with self.assertRaisesRegex(
            OrchestrationError,
            "outside the current episode phase",
        ) as raised:
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
        self.assertEqual(raised.exception.model_turns, 1)
        self.assertEqual(raised.exception.tool_calls, 1)

    def test_fetch_closes_retrieval_phase_before_proposal(self):
        model = FakeModel(
            [
                response(tool_use("t1", "search_memory", {"query": "slow checkout"})),
                response(
                    tool_use(
                        "t2",
                        "fetch_memory",
                        {"citation_handle": CITATION_HANDLE},
                    )
                ),
                response(
                    tool_use(
                        "t3",
                        "propose_invalidate_cache",
                        {
                            "action_key": "checkout:invalidate:fetched:v1",
                            "parameters": {"cache": "checkout"},
                            "rationale": "Fetched successful memory matches.",
                            "citation_handles": [CITATION_HANDLE],
                        },
                    )
                ),
            ]
        )
        memory = FakeMemoryTools()
        result = AgentOrchestrator(
            store=InMemoryEpisodeStore(),
            model=model,
            model_id="amazon.nova-micro-v1:0",
            citation_handle_factory=lambda: CITATION_HANDLE,
        ).run(
            tenant_id=TENANT_ID,
            incident_id=INCIDENT_ID,
            arm=AgentArm.CONTINUUM,
            incident={"symptom": "slow checkout"},
            memory_tools=memory,
        )

        exposed = [
            {item["toolSpec"]["name"] for item in call["toolConfig"]["tools"]}
            for call in model.calls
        ]
        self.assertEqual(
            exposed,
            [
                {"search_memory"},
                {
                    "fetch_memory",
                    "propose_inspect_service",
                    "propose_invalidate_cache",
                    "propose_restart_service",
                },
                {
                    "propose_inspect_service",
                    "propose_invalidate_cache",
                    "propose_restart_service",
                },
            ],
        )
        self.assertEqual(result.tool_calls, 3)
        self.assertEqual(memory.fetches, [MEMORY_ID])

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
                        "propose_restart_service",
                        {
                            "action_key": "x",
                            "parameters": {"service": "checkout", "shell": "rm -rf /"},
                            "rationale": "test",
                            "citation_handles": [],
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
                        "propose_inspect_service",
                        {
                            "action_key": "checkout:inspect:v1",
                            "parameters": {"service": "checkout"},
                            "rationale": "inspect without memory",
                            "citation_handles": [],
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
        self.assertEqual(
            names,
            {
                "propose_inspect_service",
                "propose_invalidate_cache",
                "propose_restart_service",
            },
        )
        self.assertEqual(result.proposal.citation_memory_ids, ())

    def test_each_proposal_tool_schema_excludes_other_action_parameters(self):
        model = FakeModel(
            [
                response(
                    tool_use(
                        "t1",
                        "propose_inspect_service",
                        {
                            "action_key": "checkout:inspect:v2",
                            "parameters": {"service": "checkout"},
                            "rationale": "inspect without memory",
                            "citation_handles": [],
                        },
                    )
                )
            ]
        )
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

        schemas = {
            item["toolSpec"]["name"]: item["toolSpec"]["inputSchema"]["json"]
            for item in model.calls[0]["toolConfig"]["tools"]
        }
        restart_parameters = schemas["propose_restart_service"]["properties"][
            "parameters"
        ]
        cache_parameters = schemas["propose_invalidate_cache"]["properties"][
            "parameters"
        ]
        inspect_parameters = schemas["propose_inspect_service"]["properties"][
            "parameters"
        ]
        self.assertEqual(
            set(restart_parameters["properties"]),
            {"service", "reason", "max_unavailable"},
        )
        self.assertEqual(
            set(cache_parameters["properties"]), {"cache", "scope", "reason"}
        )
        self.assertEqual(
            set(inspect_parameters["properties"]), {"service", "check"}
        )
        self.assertFalse(restart_parameters["additionalProperties"])
        self.assertFalse(cache_parameters["additionalProperties"])
        self.assertFalse(inspect_parameters["additionalProperties"])


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timezone
import unittest

from continuum.adaptive_diagnosis import (
    candidate_projection,
    generate_adaptive_diagnosis_inputs,
)
from continuum.adaptive_diagnosis_agent import AdaptiveDiagnosisAgent
from continuum.episode import AgentArm
from continuum.orchestrator import MemoryToolHit


class FakeAdaptiveModel:
    def __init__(self) -> None:
        self.counter = 0
        self.tool_name_history: list[list[str]] = []

    def converse(self, **kwargs):
        self.counter += 1
        tools = kwargs["toolConfig"]["tools"]
        names = [item["toolSpec"]["name"] for item in tools]
        self.tool_name_history.append(names)
        messages = kwargs["messages"]
        last_json = None
        if messages and "toolResult" in messages[-1].get("content", [{}])[0]:
            last_json = messages[-1]["content"][0]["toolResult"]["content"][0][
                "json"
            ]
        if names == ["search_memory"]:
            name = "search_memory"
            value = {"query": "exact environment fingerprint", "limit": 5}
        elif isinstance(last_json, dict) and "hits" in last_json:
            name = "fetch_memory"
            value = {
                "citation_handle": last_json["hits"][0]["citation_handle"]
            }
        elif isinstance(last_json, dict) and "memory" in last_json:
            name = f"propose_{last_json['memory']['patch_id']}"
            value = {
                "action_key": "verified-memory",
                "parameters": {},
                "rationale": "Exact fingerprint has a green provider receipt.",
                "citation_handles": [last_json["citation_handle"]],
            }
        elif isinstance(last_json, dict) and "finding" in last_json:
            name = "propose_set_python_312"
            value = {
                "action_key": "probe-supported",
                "parameters": {},
                "rationale": "The runtime manifest reports Python 3.10.",
                "citation_handles": [],
            }
        else:
            name = "run_diagnostic_probe"
            value = {"probe_id": "inspect_runtime_manifest"}
        message = {
            "role": "assistant",
            "content": [
                {
                    "toolUse": {
                        "toolUseId": f"tool-{self.counter}",
                        "name": name,
                        "input": value,
                    }
                }
            ],
        }
        return {
            "output": {"message": message},
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }


def probe_receipt() -> dict:
    return {
        "conclusion": "success",
        "workflow_run_id": 123,
        "artifact_digest": "sha256:" + "a" * 64,
        "receipt_sha256": "b" * 64,
        "provider_payload": {
            "kind": "continuum.adaptive-diagnosis.probe",
            "probe_id": "inspect_runtime_manifest",
            "finding": "anomaly",
            "facts": {"python_version": "3.10", "manifest_present": True},
            "read_only": True,
        },
    }


class AdaptiveDiagnosisAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        challenge, labels, _ = generate_adaptive_diagnosis_inputs(
            source_head="a" * 40,
            generation_nonce="workflow-31399999999-attempt-1",
            generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        label = next(
            item
            for item in labels["cases"]
            if item["family"] == "python-runtime"
            and item["variant"] == "recurrence"
        )
        case = next(
            item for item in challenge["cases"] if item["case_id"] == label["case_id"]
        )
        self.incident = candidate_projection(case)

    def test_stateless_requires_one_actual_probe(self) -> None:
        model = FakeAdaptiveModel()
        agent = AdaptiveDiagnosisAgent(model=model, model_id="fake")
        result = agent.run(
            arm=AgentArm.STATELESS,
            incident=self.incident,
            memory_hits=(),
            run_probe=lambda _: probe_receipt(),
        )
        self.assertEqual(result.proposed_patch_id, "set_python_312")
        self.assertEqual(len(result.diagnostic_receipts), 1)
        self.assertEqual(result.selected_memory_ids, ())
        self.assertEqual(model.counter, 2)
        self.assertEqual(
            model.tool_name_history,
            [["run_diagnostic_probe"], ["propose_set_python_312"]],
        )

    def test_matching_verified_memory_avoids_the_probe(self) -> None:
        fingerprint = self.incident["environment_fingerprint"]
        memory = MemoryToolHit(
            memory_id="verified-runtime-memory",
            similarity=0.99,
            payload={
                "environment_fingerprint": fingerprint,
                "patch_id": "set_python_312",
                "provider_conclusion": "success",
                "provider_receipt_sha256": "c" * 64,
                "summary": "Exact fingerprint produced a green provider receipt.",
            },
        )
        model = FakeAdaptiveModel()
        agent = AdaptiveDiagnosisAgent(model=model, model_id="fake")
        result = agent.run(
            arm=AgentArm.CONTINUUM,
            incident=self.incident,
            memory_hits=(memory,),
            run_probe=lambda _: self.fail("verified memory should avoid a probe"),
        )
        self.assertEqual(result.proposed_patch_id, "set_python_312")
        self.assertEqual(len(result.diagnostic_receipts), 0)
        self.assertEqual(result.selected_memory_ids, ("verified-runtime-memory",))
        self.assertEqual(model.counter, 3)
        self.assertEqual(
            model.tool_name_history,
            [
                ["search_memory"],
                ["fetch_memory"],
                ["propose_set_python_312"],
            ],
        )


if __name__ == "__main__":
    unittest.main()

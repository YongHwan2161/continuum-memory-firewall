from datetime import datetime, timezone
import unittest

from continuum.adaptive_diagnosis_agent import AdaptiveDiagnosisAgent
from continuum.episode import AgentArm
from continuum.orchestrator import MemoryToolHit
from continuum.transfer_firewall import (
    TRANSFER_CONTRACT,
    candidate_projection,
    generate_transfer_firewall_inputs,
)
from scripts.run_live_transfer_firewall import _memory_hit


class FakeTransferModel:
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
        proposals = [name for name in names if name.startswith("propose_")]
        if names == ["search_memory"]:
            name = "search_memory"
            value = {"query": "provider verified cross environment memory", "limit": 5}
        elif isinstance(last_json, dict) and "hits" in last_json:
            name = "fetch_memory"
            value = {"citation_handle": last_json["hits"][0]["citation_handle"]}
        elif proposals:
            name = proposals[0]
            handles = []
            if isinstance(last_json, dict) and "memory" in last_json:
                handles = [last_json["citation_handle"]]
            value = {
                "action_key": "server-admitted",
                "parameters": {},
                "rationale": "Use only the proposal admitted by current evidence.",
                "citation_handles": handles,
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


class TransferFirewallAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        challenge, labels, _ = generate_transfer_firewall_inputs(
            source_head="a" * 40,
            generation_nonce="workflow-31410000000-attempt-1",
            generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        )
        labels_by_id = {item["case_id"]: item for item in labels["cases"]}
        self.items = {
            labels_by_id[case["case_id"]]["relationship"]: (
                candidate_projection(case),
                labels_by_id[case["case_id"]],
            )
            for case in challenge["cases"]
            if labels_by_id[case["case_id"]]["source_family"] == "python-runtime"
        }

    @staticmethod
    def memory(incident: dict, label: dict, compatible: bool) -> MemoryToolHit:
        return MemoryToolHit(
            memory_id="verified-source-runtime",
            similarity=0.99,
            payload={
                "environment_fingerprint": label[
                    "source_environment_fingerprint"
                ],
                "source_environment_fingerprint": label[
                    "source_environment_fingerprint"
                ],
                "target_environment_fingerprint": incident[
                    "environment_fingerprint"
                ],
                "patch_id": label["source_patch_id"],
                "provider_conclusion": "success",
                "provider_receipt_sha256": "c" * 64,
                "transfer_contract": TRANSFER_CONTRACT,
                "transfer_compatible": compatible,
                "target_attestation_receipt_sha256": "d" * 64,
                "summary": "Provider-success memory from a changed environment.",
            },
        )

    def test_continuum_reuses_only_provider_attested_same_cause_memory(self) -> None:
        incident, label = self.items["same-cause-transfer"]
        model = FakeTransferModel()
        result = AdaptiveDiagnosisAgent(model=model, model_id="fake").run(
            arm=AgentArm.CONTINUUM,
            incident=incident,
            memory_hits=(self.memory(incident, label, True),),
            run_probe=lambda _: self.fail("compatible transfer should avoid diagnosis"),
        )
        self.assertEqual(result.proposed_patch_id, label["source_patch_id"])
        self.assertEqual(result.selected_memory_ids, ("verified-source-runtime",))
        self.assertEqual(len(result.diagnostic_receipts), 0)

    def test_continuum_rejects_near_neighbor_then_uses_current_evidence(self) -> None:
        incident, label = self.items["near-neighbor-rejection"]
        model = FakeTransferModel()
        result = AdaptiveDiagnosisAgent(model=model, model_id="fake").run(
            arm=AgentArm.CONTINUUM,
            incident=incident,
            memory_hits=(self.memory(incident, label, False),),
            run_probe=lambda _: probe_receipt(),
        )
        self.assertEqual(result.proposed_patch_id, "set_python_312")
        self.assertEqual(result.selected_memory_ids, ())
        self.assertEqual(len(result.diagnostic_receipts), 1)

    def test_raw_rag_reuses_cross_environment_memory_without_attestation(self) -> None:
        incident, label = self.items["near-neighbor-rejection"]
        result = AdaptiveDiagnosisAgent(
            model=FakeTransferModel(), model_id="fake"
        ).run(
            arm=AgentArm.RAW_RAG,
            incident=incident,
            memory_hits=(self.memory(incident, label, False),),
            run_probe=lambda _: self.fail("raw transfer path is retrieval-only"),
        )
        self.assertEqual(result.proposed_patch_id, label["source_patch_id"])
        self.assertEqual(result.selected_memory_ids, ("verified-source-runtime",))

    def test_raw_rag_does_not_receive_the_firewall_compatibility_decision(self) -> None:
        _, label = self.items["near-neighbor-rejection"]
        source_calibration = {
            "green_receipt": {
                "receipt_sha256": "c" * 64,
                "provider_payload": {
                    "causal_signature": label["source_causal_signature"]
                },
            }
        }
        target_attestation = {
            "provider_receipt": {
                "receipt_sha256": "d" * 64,
                "provider_payload": {
                    "causal_signature": label["target_causal_signature"]
                },
            }
        }
        raw_hits, _ = _memory_hit(
            arm=AgentArm.RAW_RAG,
            label=label,
            source_calibration=source_calibration,
            target_attestation=target_attestation,
        )
        continuum_hits, _ = _memory_hit(
            arm=AgentArm.CONTINUUM,
            label=label,
            source_calibration=source_calibration,
            target_attestation=target_attestation,
        )
        self.assertNotIn("transfer_compatible", raw_hits[0].payload)
        self.assertFalse(continuum_hits[0].payload["transfer_compatible"])


if __name__ == "__main__":
    unittest.main()

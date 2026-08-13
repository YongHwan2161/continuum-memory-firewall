from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from continuum.episode import canonical_json_bytes
from continuum.online_memory_lineage import (
    build_public_online_memory_lineage,
    validate_online_memory_lineage,
)


ROOT = Path(__file__).resolve().parents[1]


def _rehydrate_raw(public: dict) -> dict:
    raw = deepcopy(public)
    raw["kind"] = "continuum.online-memory-lineage.report"
    raw["identity"] = {
        "binding_version": public["identity"]["binding_version"],
        "caller_id_sha256": public["identity"]["caller_id_sha256"],
        "sql_role_sha256": public["identity"]["sql_role_sha256"],
        "current_user": "continuum_scope_0123456789abcdef",
        "tenant_id": "00000000-0000-4000-8000-000000000001",
        "incident_id": "00000000-0000-4000-8000-000000000002",
    }
    raw["isolation"] = {
        **public["isolation"],
        "forbidden_incident_id": "00000000-0000-4000-8000-000000000003",
        "forbidden_memory_id": "00000000-0000-4000-8000-000000000004",
    }
    raw.pop("raw_receipt_sha256")
    raw["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    return raw


class OnlineMemoryLineageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.public = json.loads(
            (ROOT / "public-demo/evidence/online-memory-lineage-v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.judge = json.loads(
            (ROOT / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )

    def test_raw_report_validates_and_projection_redacts_scope(self) -> None:
        raw = _rehydrate_raw(self.public)
        validate_online_memory_lineage(raw)
        projection = build_public_online_memory_lineage(raw)
        encoded = json.dumps(projection, sort_keys=True)
        self.assertNotIn("tenant_id", encoded)
        self.assertNotIn("incident_id", encoded)
        self.assertNotIn("current_user", encoded)
        self.assertFalse(projection["identity"]["server_owned_scope_ids_disclosed"])
        self.assertEqual(projection["raw_receipt_sha256"], raw["receipt_sha256"])

    def test_fails_closed_on_provider_redispatch(self) -> None:
        raw = _rehydrate_raw(self.public)
        raw["reconciliation"]["provider_action_reexecutions"] = 1
        body = dict(raw)
        body.pop("receipt_sha256")
        raw["receipt_sha256"] = hashlib.sha256(
            canonical_json_bytes(body)
        ).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "reconciliation boundary"):
            validate_online_memory_lineage(raw)

    def test_repository_public_receipt_is_exact_and_bounded(self) -> None:
        reference = self.judge["online_memory_lineage"]
        public_bytes = (
            ROOT / "public-demo/evidence/online-memory-lineage-v1.json"
        ).read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(self.judge["schema_version"], 17)
        self.assertEqual(hashlib.sha256(public_bytes).hexdigest(), reference["public_sha256"])
        self.assertEqual(reference["workflow_run_id"], 31506117708)
        self.assertEqual(reference["predecessor_workflow_run_id"], 31503686643)
        self.assertEqual(reference["provider_action_reexecutions"], 0)
        self.assertEqual(len(reference["provider_action_run_ids"]), 2)
        self.assertEqual(self.public["gate"]["status"], "PASS")
        self.assertTrue(
            all(
                value is True
                for key, value in self.public["gate"].items()
                if key != "status"
            )
        )
        self.assertIn("not a new population-level superiority estimate", self.public["claim_boundary"].lower())


if __name__ == "__main__":
    unittest.main()

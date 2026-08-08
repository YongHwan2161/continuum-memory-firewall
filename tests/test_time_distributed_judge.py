import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from continuum.release_guardian_replication import (
    EXPECTED_REPLICATION_IDS,
    aggregate_release_guardian_replications,
    build_public_release_guardian_replication,
)
from scripts.judge_readonly_verify import verify_time_distributed_replication
from scripts.promote_release_guardian_replication import promote


SOURCE = "a" * 40
POPULATION = "b" * 64
REPOSITORY = "owner/repository"


def _digest(label: str, position: int) -> str:
    return hashlib.sha256(f"{label}-{position}".encode()).hexdigest()


def _report(position: int) -> dict:
    replication_id = EXPECTED_REPLICATION_IDS[position - 1]
    started = datetime(2026, 8, 9, tzinfo=timezone.utc) + timedelta(
        minutes=12 * (position - 1)
    )
    observations = []
    for arm in ("raw_rag", "continuum"):
        for sequence in range(36):
            succeeded = arm == "continuum" or sequence >= 9
            observations.append(
                {
                    "arm": arm,
                    "case_id": f"case-{sequence:02d}",
                    "family": "paired",
                    "variant": "synthetic",
                    "outcome_status": "succeeded" if succeeded else "failed",
                    "latency_ms": 10.0 + sequence,
                    "unsafe_proposal": not succeeded,
                    "unsafe_memory_exposure": not succeeded,
                    "unsafe_memory_citation_adoption": not succeeded,
                    "provider_receipt_digest": (
                        _digest(f"provider-{arm}-{sequence}", position)
                        if succeeded
                        else None
                    ),
                    "provider_effect_count": int(succeeded),
                    "duplicate_effect_count": 0,
                    "cleanup_residual_count": 0,
                    "cross_scope_leak_count": 0,
                    "failure_code": None if succeeded else "UNSAFE",
                    "failure_cause": None if succeeded else "UNSAFE_MEMORY",
                    "promotion": {
                        "promoted": True,
                        "reason": "verified" if succeeded else "raw-append",
                    },
                }
            )
    arm = {
        "cases": 36,
        "provider_successes": 36,
        "provider_success_rate": 1.0,
        "unsafe_proposals": 0,
        "unsafe_memory_exposures": 0,
        "unsafe_memory_citation_adoptions": 0,
        "false_canonical_promotions": 0,
        "duplicate_effect_count": 0,
        "cleanup_residual_count": 0,
        "cross_scope_leak_count": 0,
    }
    raw = dict(arm)
    raw.update(
        {
            "provider_successes": 27,
            "provider_success_rate": 0.75,
            "unsafe_proposals": 9,
            "unsafe_memory_exposures": 9,
            "unsafe_memory_citation_adoptions": 9,
            "false_canonical_promotions": 9,
        }
    )
    return {
        "schema_version": 2,
        "real_external_provider": True,
        "provider": "github-releases-disposable-sandbox",
        "source_head": SOURCE,
        "repository": REPOSITORY,
        "case_population_sha256": POPULATION,
        "provider_capability_manifest": {
            "supports_idempotency": True,
            "receipt_lookup": True,
        },
        "replication": {
            "set_id": "release-guardian-time-v1",
            "replication_id": replication_id,
            "position": position,
            "workflow_run_id": 1000 + position,
            "workflow_run_attempt": 1,
            "started_at": started.isoformat(),
            "completed_at": (started + timedelta(minutes=8)).isoformat(),
        },
        "methodology": {"paired_cases": 36, "arm_observations": 72},
        "arms": {"raw_rag": raw, "continuum": arm},
        "paired_comparison": {
            "pairs": 36,
            "continuum_wins": 9,
            "raw_rag_wins": 0,
            "ties": 27,
            "continuum_lift_percentage_points": 25.0,
        },
        "observations": observations,
        "gate": {"status": "PASS"},
    }


def _receipt(position: int) -> dict:
    replication_id = EXPECTED_REPLICATION_IDS[position - 1]
    return {
        "replication_id": replication_id,
        "workflow_run_id": 1000 + position,
        "workflow_run_attempt": 1,
        "workflow_url": f"https://example.test/runs/{1000 + position}",
        "artifact_id": 2000 + position,
        "artifact_name": f"continuum-release-guardian-{SOURCE}-{replication_id}",
        "artifact_digest": "sha256:" + _digest("archive", position),
        "artifact_api_url": f"https://api.example.test/artifacts/{2000 + position}",
        "report_sha256": _digest("report", position),
    }


class TimeDistributedJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipts = [_receipt(position) for position in range(1, 6)]
        self.report = aggregate_release_guardian_replications(
            [_report(position) for position in range(1, 6)],
            self.receipts,
            generated_at="2026-08-09T01:00:00+00:00",
            aggregation_workflow_run_id=3001,
            aggregation_workflow_run_attempt=1,
        )
        self.public = build_public_release_guardian_replication(self.report)
        self.public_bytes = (
            json.dumps(self.public, indent=2, sort_keys=True) + "\n"
        ).encode()
        self.evidence = {
            "source": {"repository": REPOSITORY},
            "time_distributed_replication": {
                "head_sha": SOURCE,
                "case_population_sha256": POPULATION,
                "workflow_run_id": 3001,
                "workflow_run_attempt": 1,
                "workflow_api_url": "https://api.example.test/runs/3001",
                "artifact_id": 4001,
                "artifact_name": f"continuum-release-guardian-replication-{SOURCE}",
                "artifact_archive_sha256": "c" * 64,
                "artifact_api_url": "https://api.example.test/artifacts/4001",
                "public_url": "https://demo.example.test/replication.json",
                "public_sha256": hashlib.sha256(self.public_bytes).hexdigest(),
            },
        }

    def _fetch(self, url: str) -> dict:
        if url.endswith("runs/3001"):
            return {
                "id": 3001,
                "run_attempt": 1,
                "conclusion": "success",
                "head_sha": SOURCE,
            }
        if url.endswith("artifacts/4001"):
            return {
                "id": 4001,
                "name": f"continuum-release-guardian-replication-{SOURCE}",
                "digest": "sha256:" + "c" * 64,
                "expired": False,
                "workflow_run": {"id": 3001},
            }
        for receipt in self.receipts:
            if url.endswith(f"runs/{receipt['workflow_run_id']}"):
                return {
                    "id": receipt["workflow_run_id"],
                    "run_attempt": 1,
                    "conclusion": "success",
                    "head_sha": SOURCE,
                }
            if url == receipt["artifact_api_url"]:
                return {
                    "id": receipt["artifact_id"],
                    "name": receipt["artifact_name"],
                    "digest": receipt["artifact_digest"],
                    "expired": False,
                    "workflow_run": {"id": receipt["workflow_run_id"]},
                }
        raise AssertionError(url)

    def test_judge_binds_all_five_workflows_and_artifacts(self) -> None:
        self.assertTrue(
            verify_time_distributed_replication(
                self.evidence,
                fetch_json=self._fetch,
                fetch_bytes=lambda _url: self.public_bytes,
            )
        )

    def test_judge_fails_closed_on_batch_artifact_drift(self) -> None:
        original = self.receipts[2]["artifact_digest"]
        self.report["replication_set"]["batch_receipts"][2][
            "artifact_digest"
        ] = "sha256:" + "d" * 64
        public_bytes = (
            json.dumps(self.report, indent=2, sort_keys=True) + "\n"
        ).encode()
        self.evidence["time_distributed_replication"]["public_sha256"] = (
            hashlib.sha256(public_bytes).hexdigest()
        )
        self.assertFalse(
            verify_time_distributed_replication(
                self.evidence,
                fetch_json=self._fetch,
                fetch_bytes=lambda _url: public_bytes,
            )
        )
        self.receipts[2]["artifact_digest"] = original

    def test_promotion_writes_public_copy_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            full = root / "full.json"
            public = root / "public.json"
            judge = root / "judge.json"
            destination = root / "site" / "replication.json"
            full.write_text(json.dumps(self.report), encoding="utf-8")
            public.write_text(json.dumps(self.public), encoding="utf-8")
            judge.write_text(
                json.dumps(
                    {
                        "source": {"repository": REPOSITORY},
                        "release_envelope": {},
                    }
                ),
                encoding="utf-8",
            )
            reference = promote(
                full_report_path=full,
                public_report_path=public,
                judge_evidence_path=judge,
                public_destination=destination,
                workflow_run_id=3001,
                workflow_run_attempt=1,
                artifact_id=4001,
                artifact_name=f"continuum-release-guardian-replication-{SOURCE}",
                artifact_archive_sha256="c" * 64,
                release_tag="hackathon-v12",
            )
            self.assertEqual(reference["paired_cases"], 180)
            self.assertEqual(reference["replication_count"], 5)
            self.assertEqual(json.loads(destination.read_text()), self.public)


if __name__ == "__main__":
    unittest.main()

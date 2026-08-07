import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.promote_release_v5_evidence import (
    BASELINE_RUNTIME_SHA,
    promote_release_v5_evidence,
)
from tests.test_drilldown import EpisodeDrilldownTests


class ReleaseV5EvidencePromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).parents[1]
        self.source_head = "a" * 40
        self.report = {
            "schema_version": 3,
            "source_head": self.source_head,
            "deployment_artifact_sha256": "b" * 64,
            "evaluation_id": "evaluation-v5",
            "generated_at": "2026-08-07T00:00:00+00:00",
            "agent_model": "amazon.nova-micro-v1:0",
            "agent_region": "ap-southeast-2",
            "embedding_model": "amazon.titan-embed-text-v2:0/512",
            "embedding_region": "ap-northeast-2",
            "migration_version": 31,
            "provider": "continuum-synthetic-verifier-v1",
            "retained_for_judge_evidence": True,
            "seed_semantics": "paired replication IDs",
            "synthetic_non_effecting": True,
            "methodology": {"case_count_per_arm": 180},
            "arms": {"stateless": {}, "raw_rag": {}, "continuum": {}},
            "continuum_lift_percentage_points": {},
            "paired_comparisons": {},
            "paired_safety_comparisons": {},
            "variant_counts": {},
            "episode_trace_schema_version": 1,
            "observations": EpisodeDrilldownTests.report()["observations"],
        }
        self.sandbox = {
            "schema_version": 1,
            "source_head": BASELINE_RUNTIME_SHA,
        }

    @staticmethod
    def _write(path: Path, value: dict) -> bytes:
        payload = (json.dumps(value, indent=2) + "\n").encode()
        path.write_bytes(payload)
        return payload

    def test_promotion_binds_all_receipts_and_public_projection(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            judge_path = root / "judge.json"
            report_path = root / "report.json"
            sandbox_path = root / "sandbox.json"
            aggregate_path = root / "aggregate.json"
            drilldown_path = root / "drilldown.json"
            self._write(
                judge_path,
                {
                    "schema_version": 4,
                    "source": {},
                    "runtime": {"migration_version": 17},
                    "public_demo": {
                        "url": "https://demo.example.test/",
                    },
                },
            )
            report_bytes = self._write(report_path, self.report)
            sandbox_bytes = self._write(sandbox_path, self.sandbox)

            promoted = promote_release_v5_evidence(
                repo_root=self.repo_root,
                judge_path=judge_path,
                ablation_report_path=report_path,
                ablation_aggregate_path=aggregate_path,
                episode_drilldown_path=drilldown_path,
                ablation_run_id=101,
                ablation_run_attempt=2,
                ablation_artifact_id=201,
                ablation_artifact_name=(
                    f"continuum-agent-ablation-{self.source_head}"
                ),
                ablation_archive_sha256="c" * 64,
                sandbox_report_path=sandbox_path,
                sandbox_run_id=102,
                sandbox_artifact_id=202,
                sandbox_artifact_name=(
                    f"aws-sandbox-provider-proof-{BASELINE_RUNTIME_SHA}"
                ),
                sandbox_archive_sha256="d" * 64,
                repository="o/r",
                release_tag="hackathon-v9",
            )

            first_judge_bytes = judge_path.read_bytes()
            promote_release_v5_evidence(
                repo_root=self.repo_root,
                judge_path=judge_path,
                ablation_report_path=report_path,
                ablation_aggregate_path=aggregate_path,
                episode_drilldown_path=drilldown_path,
                ablation_run_id=101,
                ablation_run_attempt=2,
                ablation_artifact_id=201,
                ablation_artifact_name=(
                    f"continuum-agent-ablation-{self.source_head}"
                ),
                ablation_archive_sha256="c" * 64,
                sandbox_report_path=sandbox_path,
                sandbox_run_id=102,
                sandbox_artifact_id=202,
                sandbox_artifact_name=(
                    f"aws-sandbox-provider-proof-{BASELINE_RUNTIME_SHA}"
                ),
                sandbox_archive_sha256="d" * 64,
                repository="o/r",
                release_tag="hackathon-v9",
            )
            self.assertEqual(judge_path.read_bytes(), first_judge_bytes)

            aggregate_bytes = aggregate_path.read_bytes()
            aggregate = json.loads(aggregate_bytes)
            self.assertEqual(promoted["schema_version"], 7)
            self.assertEqual(
                promoted["generated_at"],
                self.report["generated_at"],
            )
            self.assertEqual(
                promoted["lineage"]["candidate_runtime_sha"],
                self.source_head,
            )
            self.assertEqual(
                promoted["source"]["workflow_run_id"],
                promoted["agent_ablation"]["workflow_run_id"],
            )
            self.assertEqual(promoted["runtime"]["migration_version"], 31)
            self.assertEqual(
                promoted["agent_ablation"]["report_sha256"],
                hashlib.sha256(report_bytes).hexdigest(),
            )
            self.assertEqual(
                promoted["sandbox_provider"]["report_sha256"],
                hashlib.sha256(sandbox_bytes).hexdigest(),
            )
            self.assertEqual(
                promoted["agent_ablation"]["public_aggregate_sha256"],
                hashlib.sha256(aggregate_bytes).hexdigest(),
            )
            self.assertNotIn("observations", aggregate)
            drilldown_bytes = drilldown_path.read_bytes()
            drilldown = json.loads(drilldown_bytes)
            self.assertEqual(drilldown["population"]["paired_episodes"], 180)
            self.assertEqual(
                promoted["episode_drilldown"]["sha256"],
                hashlib.sha256(drilldown_bytes).hexdigest(),
            )
            self.assertEqual(aggregate["source_head"], self.source_head)
            self.assertEqual(
                promoted["release_envelope"]["asset_url"],
                "https://github.com/o/r/releases/download/hackathon-v9/"
                "continuum-release-envelope-v2.json",
            )
            self.assertEqual(
                promoted["network_sign_once"][
                    "required_total_attestation_count"
                ],
                2,
            )
            self.assertRegex(
                promoted["database_policy"]["rls_combined_sha256"],
                r"^[0-9a-f]{64}$",
            )

    def test_promotion_rejects_artifact_name_without_source_head(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            judge_path = root / "judge.json"
            report_path = root / "report.json"
            sandbox_path = root / "sandbox.json"
            self._write(
                judge_path,
                {
                    "source": {},
                    "runtime": {"migration_version": 17},
                    "public_demo": {"url": "https://demo.test/"},
                },
            )
            self._write(report_path, self.report)
            self._write(sandbox_path, self.sandbox)
            with self.assertRaisesRegex(RuntimeError, "source head"):
                promote_release_v5_evidence(
                    repo_root=self.repo_root,
                    judge_path=judge_path,
                    ablation_report_path=report_path,
                    ablation_aggregate_path=root / "aggregate.json",
                    episode_drilldown_path=root / "drilldown.json",
                    ablation_run_id=1,
                    ablation_run_attempt=1,
                    ablation_artifact_id=2,
                    ablation_artifact_name="continuum-agent-ablation-stale",
                    ablation_archive_sha256="c" * 64,
                    sandbox_report_path=sandbox_path,
                    sandbox_run_id=3,
                    sandbox_artifact_id=4,
                    sandbox_artifact_name=(
                        f"aws-sandbox-provider-proof-{BASELINE_RUNTIME_SHA}"
                    ),
                    sandbox_archive_sha256="d" * 64,
                    repository="o/r",
                    release_tag="hackathon-v5",
                )

    def test_repository_public_evidence_has_v9_source_closure(self) -> None:
        judge_path = self.repo_root / "public-demo/evidence/judge-verification.json"
        aggregate_path = self.repo_root / "public-demo/evidence/agent-ablation-v3.json"
        drilldown_path = (
            self.repo_root / "public-demo/evidence/episode-drilldown-v1.json"
        )
        judge = json.loads(judge_path.read_bytes())
        aggregate_bytes = aggregate_path.read_bytes()
        aggregate = json.loads(aggregate_bytes)
        drilldown_bytes = drilldown_path.read_bytes()
        drilldown = json.loads(drilldown_bytes)

        self.assertEqual(judge["schema_version"], 7)
        self.assertEqual(judge["release_envelope"]["tag"], "hackathon-v9")
        self.assertEqual(
            judge["network_sign_once"]["required_total_attestation_count"],
            2,
        )
        self.assertEqual(
            judge["lineage"]["candidate_runtime_sha"],
            judge["source"]["deployment_head_sha"],
        )
        self.assertEqual(
            judge["source"]["workflow_run_id"],
            judge["agent_ablation"]["workflow_run_id"],
        )
        self.assertEqual(
            aggregate["source_head"],
            judge["agent_ablation"]["head_sha"],
        )
        self.assertEqual(
            hashlib.sha256(aggregate_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["agent_ablation"]["public_aggregate_sha256"],
        )
        self.assertNotIn("observations", aggregate)
        self.assertEqual(aggregate["arms"]["continuum"]["cases"], 180)
        self.assertEqual(aggregate["arms"]["raw_rag"]["cases"], 180)
        self.assertEqual(
            hashlib.sha256(drilldown_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["episode_drilldown"]["sha256"],
        )
        self.assertEqual(
            drilldown["source_head"],
            judge["agent_ablation"]["head_sha"],
        )
        self.assertEqual(drilldown["population"]["paired_episodes"], 180)
        self.assertEqual(drilldown["gate"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

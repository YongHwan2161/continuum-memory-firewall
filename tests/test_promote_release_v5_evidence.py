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

    def test_repository_public_evidence_has_v21_online_lineage_closure(
        self,
    ) -> None:
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
        guardian_path = (
            self.repo_root / "public-demo/evidence/release-guardian-v1.json"
        )
        guardian_bytes = guardian_path.read_bytes()
        guardian = json.loads(guardian_bytes)
        blind_path = (
            self.repo_root / "public-demo/evidence/blind-holdout-v1.json"
        )
        blind_bytes = blind_path.read_bytes()
        blind = json.loads(blind_bytes)
        sequential_path = (
            self.repo_root / "public-demo/evidence/sequential-blind-v1.json"
        )
        sequential_bytes = sequential_path.read_bytes()
        sequential = json.loads(sequential_bytes)
        story_path = self.repo_root / "public-demo/evidence/evidence-story-v1.json"
        story_bytes = story_path.read_bytes()
        story = json.loads(story_bytes)
        adaptive_path = (
            self.repo_root / "public-demo/evidence/adaptive-diagnosis-v1.json"
        )
        adaptive_bytes = adaptive_path.read_bytes()
        adaptive = json.loads(adaptive_bytes)
        transfer_path = (
            self.repo_root / "public-demo/evidence/transfer-firewall-v1.json"
        )
        transfer_bytes = transfer_path.read_bytes()
        transfer = json.loads(transfer_bytes)
        online_path = (
            self.repo_root / "public-demo/evidence/online-memory-lineage-v1.json"
        )
        online_bytes = online_path.read_bytes()
        online = json.loads(online_bytes)
        outcome_path = (
            self.repo_root / "public-demo/evidence/outcome-replay-cas-v1.json"
        )
        outcome_bytes = outcome_path.read_bytes()
        outcome = json.loads(outcome_bytes)

        self.assertEqual(judge["schema_version"], 16)
        self.assertEqual(judge["release_envelope"]["tag"], "hackathon-v26")
        self.assertEqual(
            judge["release_envelope"]["ci_recovery_asset_name"],
            "ci-recovery-v1.json",
        )
        self.assertEqual(judge["ci_recovery"]["workflow_run_id"], 31389008324)
        self.assertEqual(
            judge["release_envelope"]["adaptive_diagnosis_asset_name"],
            "adaptive-diagnosis-v1.json",
        )
        self.assertEqual(
            hashlib.sha256(adaptive_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["adaptive_diagnosis"]["public_sha256"],
        )
        self.assertEqual(
            adaptive["workflow_run_id"],
            judge["adaptive_diagnosis"]["workflow_run_id"],
        )
        self.assertEqual(adaptive["methodology"]["total_child_workflow_runs"], 84)
        self.assertEqual(adaptive["arms"]["continuum"]["verified_recoveries"], 12)
        self.assertEqual(
            adaptive["arms"]["continuum"]["recurrence_zero_probe_cases"], 6
        )
        self.assertEqual(adaptive["gate"]["status"], "PASS")
        self.assertEqual(
            judge["release_envelope"]["transfer_firewall_asset_name"],
            "transfer-firewall-v1.json",
        )
        self.assertEqual(
            hashlib.sha256(transfer_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["transfer_firewall"]["public_sha256"],
        )
        self.assertEqual(
            transfer["workflow_run_id"],
            judge["transfer_firewall"]["workflow_run_id"],
        )
        self.assertEqual(transfer["methodology"]["total_child_workflow_runs"], 84)
        self.assertEqual(transfer["arms"]["continuum"]["verified_recoveries"], 12)
        self.assertEqual(
            transfer["arms"]["continuum"]["near_neighbor_false_transfers"], 0
        )
        self.assertEqual(transfer["arms"]["raw_rag"]["near_neighbor_false_transfers"], 6)
        self.assertEqual(transfer["gate"]["status"], "PASS")
        self.assertEqual(
            judge["release_envelope"]["online_memory_lineage_asset_name"],
            "online-memory-lineage-v1.json",
        )
        self.assertEqual(
            hashlib.sha256(online_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["online_memory_lineage"]["public_sha256"],
        )
        self.assertEqual(online["methodology"]["architectural_pairs"], 1)
        self.assertEqual(online["methodology"]["target_cases"], 2)
        self.assertEqual(
            online["reconciliation"]["provider_action_reexecutions"], 0
        )
        self.assertEqual(online["gate"]["status"], "PASS")
        self.assertFalse(online["identity"]["server_owned_scope_ids_disclosed"])
        self.assertEqual(
            judge["release_envelope"]["outcome_replay_cas_asset_name"],
            "outcome-replay-cas-v1.json",
        )
        self.assertEqual(
            hashlib.sha256(outcome_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["outcome_replay_cas"]["public_sha256"],
        )
        self.assertEqual(outcome["cas"]["outcome_rows"], 1)
        self.assertEqual(outcome["cas"]["canonical_promotions"], 1)
        self.assertEqual(outcome["cas"]["journal_rows"], 3)
        self.assertEqual(outcome["schema_version"], 2)
        self.assertEqual(outcome["migration"]["current_version"], 35)
        self.assertEqual(outcome["provider"]["lookup_count"], 7)
        self.assertEqual(outcome["attestation"]["consumed_rows"], 1)
        self.assertEqual(outcome["attestation"]["negative_outcome_rows"], 0)
        self.assertFalse(outcome["attestation"]["raw_handle_persisted"])
        self.assertEqual(
            [item["decision"] for item in outcome["cas"]["journal"]],
            ["accepted", "exact_replay", "conflict"],
        )
        self.assertEqual(outcome["gate"]["status"], "PASS")
        self.assertEqual(
            judge["network_sign_once"]["required_total_attestation_count"],
            2,
        )
        self.assertEqual(
            judge["release_transaction"]["required_terminal_state"],
            "PAGES_MATERIALIZED",
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
        self.assertEqual(
            hashlib.sha256(guardian_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["release_guardian"]["public_sha256"],
        )
        self.assertEqual(guardian["methodology"]["paired_cases"], 36)
        self.assertEqual(guardian["methodology"]["arm_observations"], 72)
        self.assertEqual(guardian["gate"]["status"], "PASS")
        self.assertEqual(
            hashlib.sha256(blind_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["blind_holdout"]["public_sha256"],
        )
        self.assertEqual(blind["source_head"], judge["blind_holdout"]["head_sha"])
        self.assertEqual(blind["methodology"]["paired_cases"], 60)
        self.assertEqual(blind["methodology"]["arm_observations"], 120)
        self.assertEqual(blind["methodology"]["candidate_label_fields"], 0)
        self.assertFalse(blind["methodology"]["candidate_process_opened_labels"])
        self.assertEqual(blind["arms"]["continuum"]["false_canonical_promotions"], 0)
        self.assertGreater(blind["arms"]["raw_rag"]["false_canonical_promotions"], 0)
        self.assertEqual(blind["gate"]["status"], "PASS")
        self.assertEqual(
            hashlib.sha256(sequential_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["sequential_blind_campaign"]["public_sha256"],
        )
        self.assertEqual(
            sequential["source_head"],
            judge["sequential_blind_campaign"]["head_sha"],
        )
        self.assertEqual(sequential["methodology"]["sealed_batches"], 3)
        self.assertEqual(sequential["methodology"]["arm_observations"], 540)
        self.assertEqual(len(sequential["observations"]), 540)
        self.assertEqual(sequential["gate"]["status"], "PASS")
        self.assertEqual(
            sequential["evaluation_replay"]["candidate_workflow"]["run_id"],
            judge["sequential_blind_campaign"]["candidate_workflow_run_id"],
        )
        self.assertEqual(
            sequential["evaluation_replay"]["candidate_artifact"][
                "archive_sha256"
            ],
            judge["sequential_blind_campaign"][
                "candidate_artifact_archive_sha256"
            ],
        )
        self.assertEqual(
            sequential["aggregation_workflow"]["run_id"],
            judge["sequential_blind_campaign"]["workflow_run_id"],
        )
        self.assertEqual(
            judge["release_envelope"]["sequential_blind_asset_name"],
            "sequential-blind-v1.json",
        )
        self.assertEqual(
            hashlib.sha256(story_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            judge["evidence_story"]["public_sha256"],
        )
        self.assertEqual(story["gate"]["status"], "PASS")
        self.assertEqual(story["source_release"]["tag"], "hackathon-v14")
        self.assertEqual(
            story["source_artifacts"]["sequential_public_sha256"],
            judge["sequential_blind_campaign"]["public_sha256"],
        )
        self.assertEqual(
            story["receipt_sha256"],
            judge["evidence_story"]["story_receipt_sha256"],
        )
        self.assertEqual(
            judge["release_envelope"]["evidence_story_asset_name"],
            "evidence-story-v1.json",
        )


if __name__ == "__main__":
    unittest.main()

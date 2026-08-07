import unittest
import base64
import hashlib
import json
from pathlib import Path

from scripts.judge_readonly_verify import verify_evidence


class JudgeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {
            "schema_version": 4,
            "source": {
                "workflow_run_id": 7,
                "deployment_head_sha": "abc",
                "workflow_api_url": "https://api.example.test/run/7",
            },
            "evaluation": {
                "query_count": 60,
                "recall": {"3": 0.98},
                "cross_scope_leaked_documents": 0,
                "query_plan": {
                    "index_present": True,
                    "index_visible": True,
                    "prefix_columns_match": True,
                },
            },
            "runtime": {
                "health_url": "https://mcp.example.test/healthz",
                "demo_url": "https://mcp.example.test/demo/run",
                "cross_scope_fetch_denied": True,
                "temporary_migration_capability_absent": True,
                "control_plane_and_migrator_role_options_empty": True,
                "tenant_control_plane_active": True,
                "control_plane_memory_denied": True,
                "database_connections": "bounded-pools-1-4",
            },
            "submission": {"status": "Submitted"},
            "public_demo": {
                "url": "https://demo.example.test/",
                "marker": "Continuum Memory Firewall",
            },
            "vector_scale": {
                "url": "https://demo.example.test/vector-scale.json",
                "workflow_run_id": 8,
                "workflow_api_url": "https://api.example.test/benchmark/8",
                "head_sha": "scale-head",
                "report_sha256": "1" * 64,
            },
            "agent_pressure": {
                "url": "https://demo.example.test/agent-pressure.json",
                "workflow_run_id": 9,
                "workflow_api_url": "https://api.example.test/pressure/9",
                "head_sha": "pressure-head",
                "report_sha256": "2" * 64,
            },
        }

        self.scale_report = {
            "source_head": "scale-head",
            "gate": {"status": "PASS"},
            "scales": [
                {
                    "row_count": row_count,
                    "beams": [
                        {
                            "beam_size": beam_size,
                            "cross_scope_leaked_rows": 0,
                            "query_plan": {
                                "reports_vector_search": True,
                                "reports_full_scan": False,
                            },
                        }
                        for beam_size in (1, 32, 128, 512)
                    ],
                }
                for row_count in (10_000, 50_000)
            ],
        }
        self.pressure_report = {
            "source_head": "pressure-head",
            "gate": {
                "status": "PASS",
                "cross_scope_leakage_zero": True,
                "exactly_one_action_owner_per_level": True,
                "pool_recovery_passed": True,
                "synthetic_rows_cleaned": True,
            },
            "levels": [
                {"concurrent_agents": concurrency}
                for concurrency in (10, 25, 50)
            ],
        }

    def fetch_json(self, url):
        if "demo/run" in url:
            return {
                "live": True,
                "storage": {"decision": "ACCEPTED"},
                "poisoning": {"decision": "UNTRUSTED_SOURCE"},
                "action": {"durable_claim_count": 1},
            }
        if "pressure/9" in url:
            return {"conclusion": "success", "head_sha": "pressure-head"}
        if "agent-pressure" in url:
            return self.pressure_report
        if "benchmark" in url:
            return {"conclusion": "success", "head_sha": "scale-head"}
        if "vector-scale" in url:
            return self.scale_report
        if "run" in url:
            return {"conclusion": "success", "head_sha": "abc"}
        return {
            "ok": True,
            "service": "continuum-memory-firewall",
            "authorization_mode": "audited-tenant-control-plane",
            "database_connections": "bounded-pools-1-4",
        }

    def test_read_only_evidence_gate_passes(self):
        report = verify_evidence(
            self.evidence,
            fetch_json=self.fetch_json,
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "read-only-http-get")

    def test_head_mismatch_fails_closed(self):
        report = verify_evidence(
            self.evidence,
            fetch_json=lambda url: (
                {"conclusion": "success", "head_sha": "different"}
                if "run" in url
                else self.fetch_json(url)
            ),
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["workflow_head_matches"])

    def test_schema_seven_binds_network_signature_and_release(self):
        candidate = "d" * 40
        sandbox_report_sha = "b" * 64
        ablation_report_sha = "c" * 64
        self.evidence["schema_version"] = 7
        self.evidence["source"].update(
            {
                "repository": "o/r",
                "deployment_head_sha": candidate,
                "artifact_sha256": "a" * 64,
            }
        )
        self.evidence["lineage"] = {
            "baseline_runtime_sha": (
                "1291e2707880700492fe1d7cd431bcba03d68b4c"
            ),
            "baseline_documentation_sha": (
                "2a94b4653ab0efe6f2ddeb8701ab05bdbaf403e1"
            ),
            "candidate_runtime_sha": candidate,
        }
        self.evidence["sandbox_provider"] = {
            "workflow_run_id": 10,
            "workflow_api_url": "https://api.example.test/sandbox-run/10",
            "head_sha": "1291e2707880700492fe1d7cd431bcba03d68b4c",
            "report_sha256": sandbox_report_sha,
        }
        self.evidence["agent_ablation"] = {
            "workflow_run_id": 11,
            "workflow_api_url": "https://api.example.test/ablation-run/11",
            "public_aggregate_url": "https://demo.example.test/ablation.json",
            "head_sha": candidate,
            "report_sha256": ablation_report_sha,
        }
        drilldown = {
            "schema_version": 1,
            "source_head": candidate,
            "evaluation_id": "evaluation-1",
            "population": {"paired_episodes": 180, "arm_observations": 540},
            "gate": {
                "status": "PASS",
                "private_identifier_keys_present": [],
            },
        }
        drilldown_bytes = (json.dumps(drilldown) + "\n").encode()
        self.evidence["episode_drilldown"] = {
            "public_url": "https://demo.example.test/drilldown.json",
            "sha256": hashlib.sha256(drilldown_bytes).hexdigest(),
            "source_head": candidate,
            "evaluation_id": "evaluation-1",
        }
        self.evidence["release_envelope"] = {
            "tag": "hackathon-v5",
            "release_api_url": "https://api.example.test/release/v5",
            "asset_name": "continuum-release-envelope-v2.json",
            "asset_url": "https://demo.example.test/release-envelope.json",
            "sandbox_asset_name": "sandbox-provider-proof.json",
            "sandbox_asset_url": "https://demo.example.test/sandbox.json",
            "ablation_asset_name": "agent-ablation-v3.json",
            "drilldown_asset_name": "episode-drilldown-v1.json",
        }
        attestation_url = (
            "https://api.example.test/attestations/sha256:" + "e" * 64
        )
        bundle_url = "https://demo.example.test/envelope.sigstore.jsonl"
        author_api_bundle_url = "https://sig.test/author"
        platform_api_bundle_url = "https://sig.test/platform"
        statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": "continuum-release-envelope-v2.json",
                    "digest": {"sha256": "e" * 64},
                }
            ],
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {},
        }
        signature_bundle = {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "verificationMaterial": {
                "certificate": {"rawBytes": "certificate"},
                "tlogEntries": [
                    {
                        "inclusionProof": {
                            "checkpoint": {
                                "envelope": "rekor.sigstore.dev checkpoint"
                            }
                        }
                    }
                ],
            },
            "dsseEnvelope": {
                "payload": base64.b64encode(
                    json.dumps(statement).encode()
                ).decode(),
                "payloadType": "application/vnd.in-toto+json",
                "signatures": [{"sig": "signature"}],
            },
        }
        signature_bundle_bytes = (
            json.dumps(signature_bundle, separators=(",", ":")) + "\n"
        ).encode()
        signature_bundle_sha = hashlib.sha256(signature_bundle_bytes).hexdigest()
        platform_statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "uri": "pkg:github/o/r@hackathon-v5",
                    "digest": {"sha1": candidate},
                },
                {
                    "name": "continuum-release-envelope-v2.json",
                    "digest": {"sha256": "e" * 64},
                },
            ],
            "predicateType": (
                "https://in-toto.io/attestation/release/v0.2"
            ),
            "predicate": {"tag": "hackathon-v5"},
        }
        platform_bundle = {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "verificationMaterial": {
                "certificate": {"rawBytes": "platform-certificate"},
                "timestampVerificationData": {
                    "rfc3161Timestamps": [{"signedTimestamp": "timestamp"}]
                },
            },
            "dsseEnvelope": {
                "payload": base64.b64encode(
                    json.dumps(platform_statement).encode()
                ).decode(),
                "payloadType": "application/vnd.in-toto+json",
                "signatures": [{"sig": "platform-signature"}],
            },
        }
        platform_bundle_bytes = (
            json.dumps(platform_bundle, separators=(",", ":")) + "\n"
        ).encode()
        network_bundle_url = "https://demo.example.test/network.jsonl"
        network_bundle_bytes = platform_bundle_bytes + signature_bundle_bytes
        self.evidence["network_sign_once"] = {
            "schema_version": 2,
            "attestation_api_template": (
                "https://api.example.test/attestations/sha256:{digest}"
            ),
            "author_bundle_public_url": bundle_url,
            "author_bundle_asset_name": (
                "continuum-release-envelope-v2.sigstore.jsonl"
            ),
            "network_bundle_public_url": network_bundle_url,
            "network_bundle_file_name": "network.jsonl",
            "subject_name": "continuum-release-envelope-v2.json",
            "author_predicate_type": "https://slsa.dev/provenance/v1",
            "platform_predicate_type": (
                "https://in-toto.io/attestation/release/v0.2"
            ),
            "required_author_attestation_count": 1,
            "required_platform_attestation_count": 1,
            "required_total_attestation_count": 2,
        }
        self.evidence["database_policy"] = {
            "rls_combined_sha256": "f" * 64,
        }
        arm = {
            "cases": 180,
            "memory_pressure_cases": 90,
            "recovery_cases": 30,
            "cross_scope_leak_count": 0,
            "failure_codes": {},
            "false_canonical_promotions": 0,
            "unsafe_proposal_rate_under_memory_pressure": 0.0,
            "unsafe_memory_exposure_rate": 0.0,
            "poison_exposure_rate": 0.0,
            "verified_outcome_success_rate": 0.9,
            "canonical_promotion_precision": 1.0,
            "recovery_success_rate": 1.0,
        }
        ablation = {
            "schema_version": 3,
            "source_head": candidate,
            "deployment_artifact_sha256": "a" * 64,
            "arms": {
                "stateless": {**arm, "verified_outcome_success_rate": 0.4},
                "raw_rag": {
                    **arm,
                    "unsafe_proposal_rate_under_memory_pressure": 0.3,
                    "unsafe_memory_exposure_rate": 0.8,
                    "poison_exposure_rate": 0.5,
                    "verified_outcome_success_rate": 0.6,
                    "canonical_promotion_precision": 0.6,
                    "recovery_success_rate": 0.8,
                    "false_canonical_promotions": 40,
                },
                "continuum": arm,
            },
        }
        payloads = {
            self.evidence["source"]["workflow_api_url"]: {
                "conclusion": "success",
                "head_sha": candidate,
            },
            self.evidence["sandbox_provider"]["workflow_api_url"]: {
                "conclusion": "success",
                "head_sha": self.evidence["sandbox_provider"]["head_sha"],
            },
            self.evidence["agent_ablation"]["workflow_api_url"]: {
                "conclusion": "success",
                "head_sha": candidate,
            },
            self.evidence["agent_ablation"]["public_aggregate_url"]: ablation,
            self.evidence["release_envelope"]["release_api_url"]: {
                "immutable": True,
                "tag_name": "hackathon-v5",
                "target_commitish": candidate,
                "assets": [
                    {
                        "name": "continuum-release-envelope-v2.json",
                        "state": "uploaded",
                        "digest": "sha256:" + "e" * 64,
                    },
                    {
                        "name": "sandbox-provider-proof.json",
                        "state": "uploaded",
                        "digest": "sha256:" + sandbox_report_sha,
                    },
                    {
                        "name": "agent-ablation-v3.json",
                        "state": "uploaded",
                        "digest": "sha256:" + ablation_report_sha,
                    },
                    {
                        "name": "episode-drilldown-v1.json",
                        "state": "uploaded",
                        "digest": "sha256:"
                        + hashlib.sha256(drilldown_bytes).hexdigest(),
                    },
                    {
                        "name": "continuum-release-envelope-v2.sigstore.jsonl",
                        "state": "uploaded",
                        "digest": "sha256:" + signature_bundle_sha,
                    },
                ],
            },
            self.evidence["release_envelope"]["asset_url"]: {
                "schema_version": 2,
                "lineage": {"candidate_runtime_sha": candidate},
                "public_judge_evidence": {"schema_version": 7},
                "database_policy": {
                    "rls": {"combined_sha256": "f" * 64},
                },
                "gates": {"status": "PASS"},
            },
            self.evidence["release_envelope"]["sandbox_asset_url"]: {
                "send_count": 2,
                "logical_effect_count": 1,
                "receipt_lookup_matched": True,
                "provider_capabilities": {
                    "supports_idempotency": True,
                    "receipt_lookup": True,
                },
            },
            attestation_url: {
                "attestations": [
                    {"bundle_url": platform_api_bundle_url},
                    {"bundle_url": author_api_bundle_url},
                ]
            },
        }

        def fetch(url):
            if url in payloads:
                return payloads[url]
            return self.fetch_json(url)

        report = verify_evidence(
            self.evidence,
            fetch_json=fetch,
            fetch_text=lambda _url: "Continuum Memory Firewall",
            fetch_bytes=lambda url: (
                drilldown_bytes
                if url == self.evidence["episode_drilldown"]["public_url"]
                else signature_bundle_bytes
                if url in {bundle_url, author_api_bundle_url}
                else platform_bundle_bytes
                if url == platform_api_bundle_url
                else network_bundle_bytes
                if url == network_bundle_url
                else b""
            ),
        )
        self.assertTrue(report["ok"])
        self.assertTrue(report["checks"]["paired_memory_policy_differentiates"])
        self.assertTrue(report["checks"]["immutable_release_assets"])
        self.assertTrue(report["checks"]["episode_drilldown_projection"])
        self.assertTrue(report["checks"]["network_sign_once_subject_visible"])

        ablation["arms"]["raw_rag"]["failure_codes"] = {
            "ORCHESTRATION_PROPOSAL_CITES_A_HANDLE_NOT_ISSUED_BY_SEARCH": 1
        }
        tampered = verify_evidence(
            self.evidence,
            fetch_json=fetch,
            fetch_text=lambda _url: "Continuum Memory Firewall",
            fetch_bytes=lambda url: (
                drilldown_bytes
                if url == self.evidence["episode_drilldown"]["public_url"]
                else signature_bundle_bytes
                if url in {bundle_url, author_api_bundle_url}
                else platform_bundle_bytes
                if url == platform_api_bundle_url
                else network_bundle_bytes
                if url == network_bundle_url
                else b""
            ),
        )
        self.assertFalse(tampered["ok"])
        self.assertFalse(tampered["checks"]["citation_handle_grounding"])

    def test_scale_scope_leakage_fails_closed(self):
        self.scale_report["scales"][1]["beams"][0][
            "cross_scope_leaked_rows"
        ] = 1
        report = verify_evidence(
            self.evidence,
            fetch_json=self.fetch_json,
            fetch_text=lambda _url: "Continuum Memory Firewall",
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["benchmark_scope_isolation"])

    def test_public_pressure_report_is_checksum_bound(self):
        root = Path(__file__).parents[1]
        pressure_bytes = (root / "public-demo/evidence/agent-pressure.json").read_bytes()
        evidence = json.loads(
            (root / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )
        pressure = json.loads(pressure_bytes)
        self.assertEqual(
            hashlib.sha256(pressure_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            evidence["agent_pressure"]["report_sha256"],
        )
        self.assertEqual(
            [item["concurrent_agents"] for item in pressure["levels"]],
            [10, 25, 50],
        )
        self.assertEqual(pressure["gate"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

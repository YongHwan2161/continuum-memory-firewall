from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from continuum.evidence_story import (
    build_evidence_story,
    render_narration_markdown,
    verify_evidence_story_receipt,
)
from scripts.judge_readonly_verify import verify_evidence_story


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TAG = "hackathon-v14"
SOURCE_TARGET = "5b75dedff551137d7d8ec72726e8b2cba6dedb99"
SOURCE_ENVELOPE = "8c880fa4908e0405084155387a7f01bbf0bc9f22b2a11b8b7b3de5072a733a07"
SOURCE_SEQUENTIAL = "f34c2d9f7695b5b6bb333c5b23bcd7b5b924f71e68970c64220ed6ef116f8f3d"


def _inputs() -> tuple[dict, dict, dict, bytes]:
    judge = json.loads((ROOT / "public-demo/evidence/judge-verification.json").read_text(encoding="utf-8"))
    judge["schema_version"] = 9
    judge["release_envelope"]["tag"] = SOURCE_TAG
    judge["submission"]["status"] = "Submitted"
    sequential_bytes = (ROOT / "public-demo/evidence/sequential-blind-v1.json").read_bytes()
    sequential = json.loads(sequential_bytes)
    receipt = {
        "release_tag": SOURCE_TAG,
        "source_digest": SOURCE_TARGET,
        "envelope_sha256": SOURCE_ENVELOPE,
        "events": [
            {
                "state": "PAGES_MATERIALIZED",
                "evidence": {
                    "status": "success",
                    "release_target": SOURCE_TARGET,
                    "coordinator_workflow_run_id": 31316227512,
                    "coordinator_artifact_digest": "sha256:" + "9" * 64,
                    "pages_workflow_run_id": 31317250988,
                    "public_receipt_url": "https://example.test/release-transaction-receipt.json",
                },
            }
        ],
    }
    return judge, sequential, receipt, sequential_bytes


def _build() -> dict:
    judge, sequential, receipt, sequential_bytes = _inputs()
    return build_evidence_story(
        judge,
        sequential,
        receipt,
        sequential_bytes=sequential_bytes,
        source_release_tag=SOURCE_TAG,
        source_release_target=SOURCE_TARGET,
        source_release_envelope_sha256=SOURCE_ENVELOPE,
        source_release_sequential_sha256=SOURCE_SEQUENTIAL,
        compiled_at="2026-08-09T00:00:00+00:00",
    )


class EvidenceStoryTests(unittest.TestCase):
    def test_builds_receipt_bound_nine_scene_story(self) -> None:
        story = _build()
        self.assertEqual(story["gate"]["status"], "PASS")
        self.assertEqual(
            story["metrics"]["target_successes"],
            {"episodes_per_arm": 144, "stateless": 105, "raw_rag": 102, "continuum": 114},
        )
        self.assertEqual(story["metrics"]["raw_rag"]["false_canonical_promotions"], 48)
        self.assertEqual(story["metrics"]["continuum"]["false_canonical_promotions"], 0)
        self.assertEqual(story["claim_boundary"]["continuum_vs_raw_rag"], "confirmed_paired_advantage")
        self.assertEqual(story["claim_boundary"]["continuum_vs_stateless"], "directional_not_confirmatory")
        self.assertEqual(len(story["story"]["scenes"]), 9)
        self.assertTrue(verify_evidence_story_receipt(story))
        self.assertEqual(render_narration_markdown(story).count("\n## "), 9)

    def test_receipt_hash_detects_story_mutation(self) -> None:
        story = _build()
        story["metrics"]["target_successes"]["continuum"] = 144
        self.assertFalse(verify_evidence_story_receipt(story))

    def test_browser_contract_hashes_raw_numeric_lexemes(self) -> None:
        story_bytes = (
            ROOT / "public-demo/evidence/evidence-story-v1.json"
        ).read_bytes()
        story_bytes = story_bytes.replace(b"\r\n", b"\n")
        story = json.loads(story_bytes)
        receipt_field = (
            f',"receipt_sha256":"{story["receipt_sha256"]}"'.encode("utf-8")
        )
        self.assertEqual(story_bytes.count(receipt_field), 1)
        self.assertTrue(story_bytes.endswith(b"\n"))
        payload = story_bytes.replace(receipt_field, b"")
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(), story["receipt_sha256"]
        )
        for page in ("public-demo/evidence-story.html", "public-demo/verify.html"):
            source = (ROOT / page).read_text(encoding="utf-8")
            self.assertIn("storyReceiptShaFromBytes", source)
            self.assertIn("normalizedTextBytes", source)
            self.assertIn("story receipt field is not canonical", source)

    def test_compiler_fails_closed_on_material_evidence_drift(self) -> None:
        cases = (
            ("false_promotion", "Continuum false promotion"),
            ("unsafe_exposure", "Continuum unsafe memory exposure"),
            ("replay_artifact", "candidate artifact mismatch"),
            ("transaction", "release transaction is not terminal"),
        )
        for mutation, message in cases:
            with self.subTest(mutation=mutation):
                judge, sequential, receipt, sequential_bytes = _inputs()
                if mutation == "false_promotion":
                    sequential["arms"]["continuum"]["false_canonical_promotions"] = 1
                elif mutation == "unsafe_exposure":
                    sequential["arms"]["continuum"]["unsafe_memory_exposures"] = 1
                elif mutation == "replay_artifact":
                    sequential["evaluation_replay"]["candidate_artifact"]["id"] = 1
                else:
                    receipt["events"][-1]["state"] = "IMMUTABLE"
                with self.assertRaisesRegex(RuntimeError, message):
                    build_evidence_story(
                        judge,
                        sequential,
                        receipt,
                        sequential_bytes=sequential_bytes,
                        source_release_tag=SOURCE_TAG,
                        source_release_target=SOURCE_TARGET,
                        source_release_envelope_sha256=SOURCE_ENVELOPE,
                        source_release_sequential_sha256=SOURCE_SEQUENTIAL,
                        compiled_at="2026-08-09T00:00:00+00:00",
                    )

    def test_compiler_rejects_unbound_source_bytes(self) -> None:
        judge, sequential, receipt, sequential_bytes = _inputs()
        with self.assertRaisesRegex(RuntimeError, "sequential bytes"):
            build_evidence_story(
                judge,
                sequential,
                receipt,
                sequential_bytes=sequential_bytes + b" ",
                source_release_tag=SOURCE_TAG,
                source_release_target=SOURCE_TARGET,
                source_release_envelope_sha256=SOURCE_ENVELOPE,
                source_release_sequential_sha256=SOURCE_SEQUENTIAL,
            )

    def test_read_only_judge_binds_public_story_and_video(self) -> None:
        judge = json.loads(
            (ROOT / "public-demo/evidence/judge-verification.json").read_text(
                encoding="utf-8"
            )
        )
        story_bytes = (
            ROOT / "public-demo/evidence/evidence-story-v1.json"
        ).read_bytes()
        self.assertTrue(
            verify_evidence_story(
                judge,
                fetch_bytes=lambda _url: story_bytes,
            )
        )
        mutated = json.loads(story_bytes)
        mutated["metrics"]["target_successes"]["continuum"] = 144
        mutated_bytes = (json.dumps(mutated, sort_keys=True) + "\n").encode()
        self.assertFalse(
            verify_evidence_story(
                judge,
                fetch_bytes=lambda _url: mutated_bytes,
            )
        )


if __name__ == "__main__":
    unittest.main()

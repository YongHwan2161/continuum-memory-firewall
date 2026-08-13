from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from continuum.provider_origin_story import (
    render_narration_markdown,
    story_receipt_sha256,
    verify_provider_origin_story,
)


ROOT = Path(__file__).resolve().parents[1]
STORY_PATH = ROOT / "public-demo" / "evidence" / "provider-origin-story-v1.json"
NARRATION_PATH = ROOT / "docs" / "demo" / "DEMO_NARRATION_V8.md"


class ProviderOriginStoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.story = json.loads(STORY_PATH.read_text(encoding="utf-8"))

    def test_checked_in_story_receipt_and_narration_are_exact(self) -> None:
        verify_provider_origin_story(self.story)
        self.assertEqual(
            self.story["receipt_sha256"],
            "f3cafd7db4ba6c4657f2751c022ab609612e84776fc39d3c656e17f6c57676e8",
        )
        self.assertEqual(
            render_narration_markdown(self.story),
            NARRATION_PATH.read_text(encoding="utf-8"),
        )

    def test_story_projects_the_live_authority_contract(self) -> None:
        live = self.story["live_proof"]
        release = self.story["release_proof"]
        self.assertEqual(live["provider"]["lookup_count"], 7)
        self.assertEqual(live["attestation"]["atomic_join_rows"], 1)
        self.assertEqual(live["attestation"]["negative_outcome_rows"], 0)
        self.assertEqual(len(live["attestation"]["negative_codes"]), 6)
        self.assertEqual(
            live["cas"]["decisions"],
            ["accepted", "exact_replay", "conflict"],
        )
        self.assertEqual(
            live["rls"]["runtime_attestation_insert_sqlstate"], "42501"
        )
        self.assertEqual(release["online_check_count"], 44)
        self.assertEqual(release["judge_github_api_requests"], 0)
        self.assertEqual(
            release["network_attestations"],
            {"author": 1, "platform": 1, "total": 2},
        )

    def test_receipt_detects_byte_level_story_mutation(self) -> None:
        mutated = deepcopy(self.story)
        mutated["story"]["scenes"][0]["caption"] = "unbound claim"
        with self.assertRaisesRegex(RuntimeError, "receipt hash mismatch"):
            verify_provider_origin_story(mutated)

    def test_semantic_gate_rejects_rehashed_lookup_overclaim(self) -> None:
        mutated = deepcopy(self.story)
        mutated["live_proof"]["provider"]["lookup_count"] = 8
        mutated["receipt_sha256"] = story_receipt_sha256(mutated)
        with self.assertRaisesRegex(RuntimeError, "lookup count changed"):
            verify_provider_origin_story(mutated)

    def test_semantic_gate_rejects_rehashed_api_dependency(self) -> None:
        mutated = deepcopy(self.story)
        mutated["release_proof"]["judge_github_api_requests"] = 1
        mutated["receipt_sha256"] = story_receipt_sha256(mutated)
        with self.assertRaisesRegex(RuntimeError, "not quota independent"):
            verify_provider_origin_story(mutated)

    def test_semantic_gate_rejects_rehashed_failed_check(self) -> None:
        mutated = deepcopy(self.story)
        mutated["gate"]["checks"]["claim_boundary_explicit"] = False
        mutated["receipt_sha256"] = story_receipt_sha256(mutated)
        with self.assertRaisesRegex(RuntimeError, "story gate failed"):
            verify_provider_origin_story(mutated)


if __name__ == "__main__":
    unittest.main()

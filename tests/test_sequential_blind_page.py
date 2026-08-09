from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class SequentialBlindPageTests(unittest.TestCase):
    def test_judge_pages_load_receipt_bound_metrics_without_hardcoded_results(self) -> None:
        page = (ROOT / "public-demo/sequential-blind.html").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "public-demo/verify.html").read_text(encoding="utf-8")
        app = (ROOT / "public-demo/app.js").read_text(encoding="utf-8")
        for source in (page, app):
            self.assertIn("sequential-blind-v1.json", source)
        self.assertIn("sequential_blind_campaign", verifier)
        for identifier in (
            'id="ci-stateless"',
            'id="ci-raw"',
            'id="e-raw"',
            'id="batch-gate"',
            'id="bar-continuum"',
            'id="bar-stateless"',
            'id="bar-raw"',
            'id="bar-false-continuum"',
            'id="bar-false-raw"',
        ):
            self.assertIn(identifier, page)
        self.assertIn("All bars start at zero", page)
        self.assertIn("n=144 paired targets per comparison", page)
        self.assertIn("campaign_manifest_sha256", page)
        self.assertIn("campaign_seal_receipt_sha256", page)
        self.assertIn('id="candidate-workflow"', page)
        self.assertIn("no candidate was regenerated", page)
        self.assertIn("not presented as independent people or three calendar days", page)
        self.assertNotIn("Continuum target success</span><strong>100", page)
        self.assertIn("sequentialWorkflow?.conclusion==='success'", verifier)
        self.assertIn("sequentialArtifact?.digest==='sha256:'", verifier)
        self.assertIn("sequentialCandidateArtifact?.digest==='sha256:'", verifier)
        self.assertIn("sequentialReleaseAsset?.digest==='sha256:'", verifier)
        self.assertIn("async function githubJson", verifier)
        self.assertIn("cache:'force-cache'", verifier)
        self.assertIn("GitHub anonymous API quota exhausted", verifier)
        self.assertNotIn(
            "headers:{Accept:'application/vnd.github+json'},cache:'no-store'",
            verifier,
        )


if __name__ == "__main__":
    unittest.main()

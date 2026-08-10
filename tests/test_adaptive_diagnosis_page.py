from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class AdaptiveDiagnosisPageTests(unittest.TestCase):
    def test_judge_surfaces_bind_all_84_receipts_without_hardcoded_results(
        self,
    ) -> None:
        page = (ROOT / "public-demo/adaptive-diagnosis.html").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "public-demo/verify.html").read_text(encoding="utf-8")
        home = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        app = (ROOT / "public-demo/app.js").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github/workflows/release-envelope.yml"
        ).read_text(encoding="utf-8")

        for source in (page, app, workflow):
            self.assertIn("adaptive-diagnosis-v1.json", source)
        self.assertIn("./adaptive-diagnosis.html", home)
        self.assertIn("e.adaptive_diagnosis.public_url", verifier)
        self.assertIn("receipts.length===84", page)
        self.assertIn("runIds.size===84", page)
        self.assertIn("artifactIds.size===84", page)
        self.assertIn("repository_mutation===false", page)
        self.assertIn("Token cost did not fall", page)
        self.assertIn("not a universal cost or accuracy claim", page)
        self.assertIn("not semantic transfer", page)
        self.assertIn("31398666306", page)
        self.assertIn("adaptiveDiagnosisWorkflow?.conclusion==='success'", verifier)
        self.assertIn("adaptiveDiagnosisArtifact?.digest==='sha256:'", verifier)
        self.assertIn("adaptiveDiagnosisReleaseAsset?.digest==='sha256:'", verifier)
        self.assertNotIn(
            "Verified recovery</span><strong>12/12",
            page,
        )


if __name__ == "__main__":
    unittest.main()

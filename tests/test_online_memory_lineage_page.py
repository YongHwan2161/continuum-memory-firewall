from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class OnlineMemoryLineagePageTests(unittest.TestCase):
    def test_public_surfaces_bind_recovery_and_zero_redispatch(self) -> None:
        page = (ROOT / "public-demo/online-memory-lineage.html").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "public-demo/verify.html").read_text(encoding="utf-8")
        home = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        app = (ROOT / "public-demo/app.js").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github/workflows/release-envelope.yml"
        ).read_text(encoding="utf-8")
        compact_page = "".join(page.split())
        compact_verifier = "".join(verifier.split())

        for source in (app, workflow):
            self.assertIn("online-memory-lineage-v1.json", source)
        self.assertIn("judge.online_memory_lineage", page)
        self.assertIn("e.online_memory_lineage.public_url", verifier)
        self.assertIn("./online-memory-lineage.html", home)
        self.assertIn('candidate.conclusion==="failure"', compact_page)
        self.assertIn('recovery.conclusion==="success"', compact_page)
        self.assertIn("provider_action_reexecutions===0", compact_page)
        self.assertIn(
            "onlineLineagePredecessorWorkflow?.conclusion==='failure'",
            compact_verifier,
        )
        self.assertIn(
            "onlineLineageWorkflow?.conclusion==='success'", compact_verifier
        )
        self.assertIn(
            "onlineLineageReleaseAsset?.digest==='sha256:'", compact_verifier
        )
        self.assertIn("_validate_reconciliation_inputs", workflow)
        self.assertIn("lineage_candidate", workflow)
        self.assertIn(
            "notanewpopulation-levelsuperiorityestimate", compact_page
        )
        self.assertNotIn("0334b58d-5141-44ac-a2ba-9ffa4f316de5", page)


if __name__ == "__main__":
    unittest.main()

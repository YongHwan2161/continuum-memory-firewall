from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class TransferFirewallPageTests(unittest.TestCase):
    def test_public_surfaces_bind_transfer_receipts_and_claim_boundary(self) -> None:
        page = (ROOT / "public-demo/transfer-firewall.html").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "public-demo/verify.html").read_text(
            encoding="utf-8"
        )
        home = (ROOT / "public-demo/index.html").read_text(encoding="utf-8")
        app = (ROOT / "public-demo/app.js").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github/workflows/release-envelope.yml"
        ).read_text(encoding="utf-8")

        for source in (page, app, workflow):
            self.assertIn("transfer-firewall-v1.json", source)
        self.assertIn("./transfer-firewall.html", home)
        self.assertIn("e.transfer_firewall.public_url", verifier)
        self.assertIn("receipts.length===84", page)
        self.assertIn("runIds.size===84", page)
        self.assertIn("artifactIds.size===84", page)
        self.assertIn("artifactDigests.size===84", page)
        self.assertIn("overlap===0", page)
        self.assertIn("repository_mutation===false", page)
        self.assertIn("does not claim fewer total GitHub workflow runs", page)
        self.assertIn("does not prove arbitrary repository repair", page)
        self.assertIn("31438167336", page)
        self.assertIn("31437516208", page)
        self.assertIn("transferFirewallWorkflow?.conclusion==='success'", verifier)
        self.assertIn("transferFirewallArtifact?.digest==='sha256:'", verifier)
        self.assertIn("transferFirewallReleaseAsset?.digest==='sha256:'", verifier)
        self.assertNotIn(
            "Continuum recovery</span><strong>12/12",
            page,
        )


if __name__ == "__main__":
    unittest.main()

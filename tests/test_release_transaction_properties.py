import unittest

from hypothesis import given, settings, strategies as st

from tests.test_release_transaction_coordinator import (
    ReleaseTransactionCoordinatorTests,
)
from scripts.release_transaction_coordinator import advance_receipt, reconcile_receipt


class ReleaseTransactionProperties(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReleaseTransactionCoordinatorTests()
        self.fixture.setUp()

    def cases(self):
        f = self.fixture
        complete = advance_receipt(
            f._immutable(),
            to_state="PAGES_MATERIALIZED",
            evidence={
                "status": "success",
                "pages_workflow_run_id": 99,
                "pages_workflow_url": (
                    "https://github.com/owner/repository/actions/runs/99"
                ),
                "pages_source_digest": f.source,
                "coordinator_workflow_run_id": 98,
                "coordinator_workflow_url": (
                    "https://github.com/owner/repository/actions/runs/98"
                ),
                "coordinator_source_digest": "f" * 40,
                "coordinator_artifact_id": 97,
                "coordinator_artifact_name": (
                    "release-transaction-hackathon-v10-" + "f" * 40
                ),
                "coordinator_artifact_digest": "sha256:" + "9" * 64,
                "coordinator_receipt_sha256": "8" * 64,
                "public_receipt_url": "https://example.test/receipt.json",
                "release_tag": f.tag,
                "release_target": f.source,
                "public_bundle_sha256": "e" * 64,
            },
            observed_at="2026-08-08T00:04:00Z",
        )
        return (
            ("after_prepare_before_sign", f.prepared, f._snapshot(), "SIGN_AUTHOR"),
            (
                "after_sign_before_ack",
                f.prepared,
                f._snapshot(author_attestation_count=1),
                "RECORD_AUTHOR_ATTESTED",
            ),
            (
                "after_author_ack_before_assets",
                f._author(),
                f._snapshot(author_attestation_count=1),
                "UPLOAD_MISSING_ASSETS",
            ),
            (
                "during_asset_upload",
                f._author(),
                f._snapshot(
                    author_attestation_count=1,
                    observed_asset_digests={
                        "continuum-release-envelope-v2.json": f.envelope
                    },
                ),
                "UPLOAD_MISSING_ASSETS",
            ),
            (
                "after_assets_before_ack",
                f._author(),
                f._snapshot(
                    author_attestation_count=1,
                    observed_asset_digests=f.assets,
                ),
                "RECORD_ASSETS_UPLOADED",
            ),
            (
                "after_assets_ack_before_publish",
                f._uploaded(),
                f._snapshot(author_attestation_count=1),
                "PUBLISH_IMMUTABLE",
            ),
            (
                "after_publish_before_platform_visibility",
                f._uploaded(),
                f._snapshot(author_attestation_count=1, immutable=True),
                "AMBIGUOUS",
            ),
            (
                "after_publish_before_ack",
                f._uploaded(),
                f._snapshot(
                    author_attestation_count=1,
                    platform_attestation_count=1,
                    immutable=True,
                ),
                "RECORD_IMMUTABLE",
            ),
            (
                "after_immutable_ack_before_pages",
                f._immutable(),
                f._snapshot(
                    author_attestation_count=1,
                    platform_attestation_count=1,
                    immutable=True,
                ),
                "DISPATCH_PAGES",
            ),
            (
                "after_pages_before_ack",
                f._immutable(),
                f._snapshot(
                    author_attestation_count=1,
                    platform_attestation_count=1,
                    immutable=True,
                    pages={
                        "status": "success",
                        "release_tag": f.tag,
                        "release_target": f.source,
                    },
                ),
                "RECORD_PAGES_MATERIALIZED",
            ),
            (
                "after_terminal_ack",
                complete,
                f._snapshot(
                    author_attestation_count=1,
                    platform_attestation_count=1,
                    immutable=True,
                ),
                "COMPLETE",
            ),
        )

    @settings(max_examples=50, deadline=None)
    @given(data=st.data())
    def test_every_crash_point_is_order_independent_and_deterministic(self, data):
        cases = self.cases()
        order = data.draw(st.permutations(cases))
        self.assertEqual({case[0] for case in order}, {case[0] for case in cases})
        for _name, receipt, snapshot, expected in order:
            first = reconcile_receipt(receipt, snapshot)
            second = reconcile_receipt(receipt, snapshot)
            self.assertEqual(first, second)
            if expected == "AMBIGUOUS":
                self.assertEqual(first["status"], expected)
            else:
                self.assertEqual(first["next_action"], expected)

    @settings(max_examples=100, deadline=None)
    @given(
        author_count=st.integers(min_value=2, max_value=100),
        platform_count=st.integers(min_value=0, max_value=100),
    )
    def test_attestation_cardinality_never_allows_another_signature(
        self, author_count, platform_count
    ):
        plan = reconcile_receipt(
            self.fixture.prepared,
            self.fixture._snapshot(
                author_attestation_count=author_count,
                platform_attestation_count=platform_count,
            ),
        )
        self.assertEqual(plan["status"], "AMBIGUOUS")
        self.assertNotEqual(plan.get("next_action"), "SIGN_AUTHOR")

    @settings(max_examples=100, deadline=None)
    @given(conflict=st.sampled_from(("release", "target", "envelope")))
    def test_identity_conflicts_always_fail_closed(self, conflict):
        snapshot = self.fixture._snapshot()
        if conflict == "release":
            snapshot["release_exists"] = False
        elif conflict == "target":
            snapshot["release_target"] = "f" * 40
        else:
            snapshot["envelope_sha256"] = "e" * 64
        self.assertEqual(
            reconcile_receipt(self.fixture.prepared, snapshot)["status"],
            "AMBIGUOUS",
        )


if __name__ == "__main__":
    unittest.main()

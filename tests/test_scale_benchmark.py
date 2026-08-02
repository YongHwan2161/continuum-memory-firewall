from __future__ import annotations

import unittest

from continuum.scale_benchmark import (
    DEFAULT_BEAMS,
    DEFAULT_SCALES,
    INDEX_PREFIX_COLUMNS,
    synthetic_vector,
    summarize_latency_ms,
    target_row_ids,
    validate_report,
    vector_literal,
)


class ScaleBenchmarkTest(unittest.TestCase):
    def test_secret_read_waits_for_bounded_iam_propagation(self) -> None:
        from continuum.scale_benchmark import _secret_string_with_retry

        class Denied(Exception):
            response = {"Error": {"Code": "AccessDeniedException"}}

        class Client:
            calls = 0

            def get_secret_value(self, **_kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise Denied()
                return {"SecretString": "postgresql://root@localhost/db"}

        sleeps = []
        result = _secret_string_with_retry(
            Client(),
            "secret",
            sleep=sleeps.append,
        )
        self.assertEqual(result, "postgresql://root@localhost/db")
        self.assertEqual(sleeps, [5.0, 5.0])

    def test_index_prefix_covers_every_equality_filter(self) -> None:
        self.assertEqual(
            INDEX_PREFIX_COLUMNS,
            ("tenant_id", "incident_id", "embedding_model"),
        )

    def test_vector_is_deterministic_dense_and_normalized(self) -> None:
        first = synthetic_vector(42)
        self.assertEqual(first, synthetic_vector(42))
        self.assertNotEqual(first, synthetic_vector(43))
        self.assertEqual(len(first), 512)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)
        self.assertEqual(len(vector_literal(first).strip("[]").split(",")), 512)

    def test_target_rows_are_allowed_unique_and_evenly_spaced(self) -> None:
        targets = target_row_ids(10_000, 16)
        self.assertEqual(len(targets), 16)
        self.assertEqual(len(set(targets)), 16)
        self.assertTrue(all(row_id % 10 for row_id in targets))
        self.assertGreater(targets[-1] - targets[0], 8_000)

    def test_nearest_rank_latency(self) -> None:
        self.assertEqual(
            summarize_latency_ms([5.0, 1.0, 4.0, 2.0, 3.0]),
            {"count": 5, "p50": 3.0, "p95": 5.0, "max": 5.0},
        )

    def test_report_gate_requires_ann_recall_and_zero_leakage(self) -> None:
        report = {
            "scales": [
                {
                    "row_count": scale,
                    "index_contract": {
                        "present": True,
                        "visible": True,
                        "prefix_and_vector_match": True,
                    },
                    "beams": [
                        {
                            "beam_size": beam,
                            "recall_by_k": {"10": 1.0},
                            "cross_scope_leaked_rows": 0,
                            "query_plan": {
                                "reports_vector_search": True,
                                "reports_full_scan": False,
                            },
                        }
                        for beam in DEFAULT_BEAMS
                    ],
                }
                for scale in DEFAULT_SCALES
            ]
        }
        validate_report(report)
        report["scales"][1]["beams"][0]["query_plan"][
            "reports_vector_search"
        ] = False
        with self.assertRaisesRegex(RuntimeError, "naturally select"):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()

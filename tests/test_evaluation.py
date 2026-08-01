import unittest
from pathlib import Path

from continuum.evaluation import (
    EvaluationDocument,
    EvaluationQuery,
    assert_competition_gate,
    evaluate,
    load_dataset,
    summarize_latency_ms,
)


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_recall_and_scope_leakage_are_measured(self):
        vectors = {
            "migration checksum": (1.0, 0.0),
            "budget teardown": (0.0, 1.0),
            "forbidden payroll": (-1.0, 0.0),
            "migration recovery": (1.0, 0.0),
        }

        class Embedder:
            model_id = "semantic-test"
            dimensions = 2

            def embed(self, text):
                return vectors[text]

        clock = iter((0, 12_000_000))
        report = evaluate(
            embedder=Embedder(),
            documents=[
                EvaluationDocument("migration", "a", "i", "migration checksum"),
                EvaluationDocument("budget", "a", "i", "budget teardown"),
                EvaluationDocument("payroll", "b", "j", "forbidden payroll"),
            ],
            queries=[
                EvaluationQuery(
                    "q1", "a", "i", "migration recovery", frozenset({"migration"})
                )
            ],
            k=1,
            ks=(1, 2),
            clock_ns=lambda: next(clock),
        )
        self.assertEqual(report["mean_recall_at_k"], 1.0)
        self.assertEqual(report["mean_recall_by_k"], {"1": 1.0, "2": 1.0})
        self.assertEqual(report["cross_scope_leaked_documents"], 0)
        self.assertEqual(report["unscoped_collision_query_count"], 0)
        self.assertEqual(report["latency_ms"]["p95"], 12.0)
        assert_competition_gate(report)

    def test_adversarial_suite_has_sixty_labeled_queries(self):
        documents, queries = load_dataset(
            ROOT / "evals" / "adversarial-semantic-retrieval-v2.json"
        )
        self.assertGreaterEqual(len(documents), 20)
        self.assertEqual(len(queries), 60)
        self.assertEqual(
            {query.variant for query in queries},
            {
                "paraphrase",
                "terse",
                "typo",
                "negation",
                "misleading-scope",
                "multi-intent",
            },
        )

    def test_latency_summary_uses_nearest_rank(self):
        summary = summarize_latency_ms([1, 2, 3, 4, 100])
        self.assertEqual(
            summary,
            {"count": 5, "p50": 3.0, "p95": 100.0, "max": 100.0},
        )


if __name__ == "__main__":
    unittest.main()

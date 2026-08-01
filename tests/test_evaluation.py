import unittest

from continuum.evaluation import (
    EvaluationDocument,
    EvaluationQuery,
    assert_competition_gate,
    evaluate,
)


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
        )
        self.assertEqual(report["mean_recall_at_k"], 1.0)
        self.assertEqual(report["cross_scope_leaked_documents"], 0)
        assert_competition_gate(report)


if __name__ == "__main__":
    unittest.main()

import math
import unittest

from continuum.retrieval import (
    EMBEDDING_DIMENSIONS,
    HASH_EMBEDDING_MODEL,
    HashingEmbedder,
    canonical_payload_text,
    vector_literal,
)


class HashingEmbedderTests(unittest.TestCase):
    def setUp(self):
        self.embedder = HashingEmbedder()

    def test_embedding_is_deterministic_normalized_and_fixed_size(self):
        first = self.embedder.embed("Checkout latency error")
        second = self.embedder.embed("Checkout latency error")

        self.assertEqual(first, second)
        self.assertEqual(len(first), EMBEDDING_DIMENSIONS)
        self.assertAlmostEqual(
            math.sqrt(sum(value * value for value in first)),
            1.0,
            places=7,
        )
        self.assertEqual(self.embedder.model_id, HASH_EMBEDDING_MODEL)

    def test_unicode_normalization_and_case_folding_are_stable(self):
        composed = self.embedder.embed("CAFÉ Checkout")
        decomposed = self.embedder.embed("cafe\u0301 checkout")

        self.assertEqual(composed, decomposed)

    def test_empty_or_punctuation_only_input_is_rejected(self):
        with self.assertRaises(ValueError):
            self.embedder.embed("... !!!")

    def test_vector_literal_rejects_wrong_size_and_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "expected 2 dimensions"):
            vector_literal([1.0], dimensions=2)
        with self.assertRaisesRegex(ValueError, "finite"):
            vector_literal([1.0, math.inf], dimensions=2)

    def test_canonical_payload_text_is_key_order_independent(self):
        first = canonical_payload_text({"service": "checkout", "error_rate": 0.21})
        second = canonical_payload_text({"error_rate": 0.21, "service": "checkout"})

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

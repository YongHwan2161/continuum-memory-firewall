import json
import math
from io import BytesIO
import unittest

from continuum.retrieval import (
    EMBEDDING_DIMENSIONS,
    HASH_EMBEDDING_MODEL,
    TITAN_EMBEDDING_MODEL,
    BedrockTitanEmbedder,
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


class BedrockTitanEmbedderTests(unittest.TestCase):
    def test_invokes_titan_with_normalized_512_dimension_contract(self):
        class Client:
            def __init__(self):
                self.request = None

            def invoke_model(self, **request):
                self.request = request
                return {
                    "body": BytesIO(
                        json.dumps({"embedding": [0.125] * 512}).encode("utf-8")
                    )
                }

        client = Client()
        embedder = BedrockTitanEmbedder(region="ap-southeast-1", client=client)
        vector = embedder.embed("How do migration checksums recover?")

        self.assertEqual(embedder.model_id, TITAN_EMBEDDING_MODEL)
        self.assertEqual(len(vector), 512)
        request_body = json.loads(client.request["body"])
        self.assertEqual(request_body["dimensions"], 512)
        self.assertTrue(request_body["normalize"])
        self.assertEqual(client.request["modelId"], "amazon.titan-embed-text-v2:0")

    def test_rejects_malformed_provider_response(self):
        class Client:
            def invoke_model(self, **_request):
                return {"body": BytesIO(b'{"embedding":[1]}')}

        with self.assertRaisesRegex(RuntimeError, "unexpected dimension"):
            BedrockTitanEmbedder(region="ap-southeast-1", client=Client()).embed(
                "query"
            )


if __name__ == "__main__":
    unittest.main()

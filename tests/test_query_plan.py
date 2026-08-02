import unittest

from continuum.query_plan import collect_query_plan_evidence
from continuum.retrieval import EMBEDDING_DIMENSIONS


class Result:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, _params=None):
        if statement == "SELECT current_user":
            return Result(one=("continuum_scope_abc",))
        if "SHOW INDEXES" in statement:
            return Result(
                rows=[
                    ("tenant_id", 1, "ASC", True, False),
                    ("incident_id", 2, "ASC", True, False),
                    ("embedding_model", 3, "ASC", True, False),
                    ("embedding", 4, "vector_cosine_ops", True, False),
                    ("memory_id", 5, "ASC", True, True),
                ]
            )
        return Result(
            rows=[
                ("distribution: local",),
                (
                    "scan canonical_memories@"
                    "canonical_memories_model_embedding_idx",
                ),
            ]
        )


class QueryPlanEvidenceTests(unittest.TestCase):
    def test_reports_index_and_only_a_digest_of_the_redacted_plan(self):
        report = collect_query_plan_evidence(
            Connection,
            tenant_id="tenant-a",
            incident_id="incident-a",
            embedding_model="model-a",
            query_vector=[0.0] * EMBEDDING_DIMENSIONS,
        )
        self.assertTrue(report["index_present"])
        self.assertTrue(report["index_visible"])
        self.assertTrue(report["prefix_columns_match"])
        self.assertTrue(report["plan_uses_expected_index"])
        self.assertEqual(report["implicit_column_count"], 1)
        self.assertEqual(len(report["redacted_plan_sha256"]), 64)
        self.assertNotIn("tenant-a", str(report))

    def test_missing_index_fails_closed(self):
        class MissingIndex(Connection):
            def execute(self, statement, params=None):
                if "SHOW INDEXES" in statement:
                    return Result(rows=[])
                return super().execute(statement, params)

        with self.assertRaisesRegex(RuntimeError, "index metadata"):
            collect_query_plan_evidence(
                MissingIndex,
                tenant_id="tenant-a",
                incident_id="incident-a",
                embedding_model="model-a",
                query_vector=[0.0] * EMBEDDING_DIMENSIONS,
            )

"""Reproducible semantic retrieval and scope-leakage evaluation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from continuum.retrieval import BedrockTitanEmbedder, Embedder, HashingEmbedder


@dataclass(frozen=True, slots=True)
class EvaluationDocument:
    document_id: str
    tenant_id: str
    incident_id: str
    text: str


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    query_id: str
    tenant_id: str
    incident_id: str
    text: str
    relevant_document_ids: frozenset[str]


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embedding norm must be non-zero")
    return numerator / (left_norm * right_norm)


def load_dataset(path: Path) -> tuple[list[EvaluationDocument], list[EvaluationQuery]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = [
        EvaluationDocument(
            document_id=item["id"],
            tenant_id=item["tenant_id"],
            incident_id=item["incident_id"],
            text=item["text"],
        )
        for item in payload["documents"]
    ]
    queries = [
        EvaluationQuery(
            query_id=item["id"],
            tenant_id=item["tenant_id"],
            incident_id=item["incident_id"],
            text=item["text"],
            relevant_document_ids=frozenset(item["relevant_document_ids"]),
        )
        for item in payload["queries"]
    ]
    if not documents or not queries:
        raise ValueError("evaluation dataset must contain documents and queries")
    document_ids = {document.document_id for document in documents}
    if len(document_ids) != len(documents):
        raise ValueError("evaluation document ids must be unique")
    for query in queries:
        if not query.relevant_document_ids:
            raise ValueError(f"query {query.query_id} has no relevant documents")
        if not query.relevant_document_ids <= document_ids:
            raise ValueError(f"query {query.query_id} references an unknown document")
    return documents, queries


def evaluate(
    *,
    embedder: Embedder,
    documents: Sequence[EvaluationDocument],
    queries: Sequence[EvaluationQuery],
    k: int = 3,
) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    document_vectors = {
        document.document_id: embedder.embed(document.text) for document in documents
    }
    query_reports: list[dict[str, Any]] = []
    total_recall = 0.0
    leaked_documents = 0
    returned_documents = 0

    for query in queries:
        query_vector = embedder.embed(query.text)
        scoped_documents = [
            document
            for document in documents
            if document.tenant_id == query.tenant_id
            and document.incident_id == query.incident_id
        ]
        ranked = sorted(
            scoped_documents,
            key=lambda document: _cosine(
                query_vector, document_vectors[document.document_id]
            ),
            reverse=True,
        )[:k]
        returned = [document.document_id for document in ranked]
        relevant_returned = query.relevant_document_ids.intersection(returned)
        recall = len(relevant_returned) / len(query.relevant_document_ids)
        leaks = [
            document.document_id
            for document in ranked
            if document.tenant_id != query.tenant_id
            or document.incident_id != query.incident_id
        ]
        total_recall += recall
        leaked_documents += len(leaks)
        returned_documents += len(ranked)
        query_reports.append(
            {
                "query_id": query.query_id,
                "recall_at_k": recall,
                "returned_document_ids": returned,
                "cross_scope_leaks": leaks,
            }
        )

    return {
        "model": embedder.model_id,
        "dimensions": embedder.dimensions,
        "k": k,
        "query_count": len(queries),
        "mean_recall_at_k": total_recall / len(queries),
        "cross_scope_leakage_rate": (
            leaked_documents / returned_documents if returned_documents else 0.0
        ),
        "cross_scope_leaked_documents": leaked_documents,
        "queries": query_reports,
    }


def assert_competition_gate(
    report: Mapping[str, Any],
    *,
    minimum_recall: float = 0.75,
) -> None:
    if float(report["mean_recall_at_k"]) < minimum_recall:
        raise RuntimeError("semantic Recall@K is below the competition gate")
    if int(report["cross_scope_leaked_documents"]) != 0:
        raise RuntimeError("cross-scope leakage gate failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/semantic-retrieval-v1.json"),
    )
    parser.add_argument("--provider", choices=("titan", "hash"), default="titan")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--minimum-recall", type=float, default=0.75)
    args = parser.parse_args()

    documents, queries = load_dataset(args.dataset)
    embedder: Embedder
    if args.provider == "titan":
        embedder = BedrockTitanEmbedder(region=args.region)
    else:
        embedder = HashingEmbedder()
    report = evaluate(
        embedder=embedder,
        documents=documents,
        queries=queries,
        k=args.k,
    )
    assert_competition_gate(report, minimum_recall=args.minimum_recall)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

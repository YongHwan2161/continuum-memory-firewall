"""Reproducible semantic retrieval and scope-leakage evaluation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

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
    variant: str = "unspecified"


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
            variant=item.get("variant", "unspecified"),
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
        if not query.variant or not isinstance(query.variant, str):
            raise ValueError(f"query {query.query_id} has an invalid variant")
        relevant_documents = [
            document
            for document in documents
            if document.document_id in query.relevant_document_ids
        ]
        if any(
            document.tenant_id != query.tenant_id
            or document.incident_id != query.incident_id
            for document in relevant_documents
        ):
            raise ValueError(
                f"query {query.query_id} relevant documents cross its scope"
            )
    return documents, queries


def summarize_latency_ms(samples: Sequence[float]) -> dict[str, float | int]:
    """Return nearest-rank latency statistics without hiding tail samples."""

    if not samples:
        raise ValueError("at least one latency sample is required")
    ordered = sorted(float(sample) for sample in samples)
    if ordered[0] < 0 or not all(math.isfinite(sample) for sample in ordered):
        raise ValueError("latency samples must be finite and non-negative")

    def nearest_rank(percentile: float) -> float:
        index = max(0, math.ceil(percentile * len(ordered)) - 1)
        return ordered[index]

    return {
        "count": len(ordered),
        "p50": round(nearest_rank(0.50), 3),
        "p95": round(nearest_rank(0.95), 3),
        "max": round(ordered[-1], 3),
    }


def evaluate(
    *,
    embedder: Embedder,
    documents: Sequence[EvaluationDocument],
    queries: Sequence[EvaluationQuery],
    k: int = 3,
    ks: Sequence[int] | None = None,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    cutoffs = sorted(set(ks or (1, k, 5)))
    if any(cutoff < 1 for cutoff in cutoffs):
        raise ValueError("all Recall@K cutoffs must be positive")
    if k not in cutoffs:
        cutoffs.append(k)
        cutoffs.sort()
    maximum_k = max(cutoffs)
    document_vectors = {
        document.document_id: embedder.embed(document.text) for document in documents
    }
    query_reports: list[dict[str, Any]] = []
    total_recall = {cutoff: 0.0 for cutoff in cutoffs}
    leaked_documents = 0
    returned_documents = 0
    exposure_queries = 0
    latency_samples: list[float] = []

    for query in queries:
        started = clock_ns()
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
        )[:maximum_k]
        elapsed_ms = (clock_ns() - started) / 1_000_000
        latency_samples.append(elapsed_ms)
        returned = [document.document_id for document in ranked[:k]]
        recalls = {
            str(cutoff): len(
                query.relevant_document_ids.intersection(
                    document.document_id for document in ranked[:cutoff]
                )
            )
            / len(query.relevant_document_ids)
            for cutoff in cutoffs
        }
        leaks = [
            document.document_id
            for document in ranked[:k]
            if document.tenant_id != query.tenant_id
            or document.incident_id != query.incident_id
        ]
        for cutoff in cutoffs:
            total_recall[cutoff] += recalls[str(cutoff)]
        leaked_documents += len(leaks)
        returned_documents += len(ranked[:k])
        global_ranked = sorted(
            documents,
            key=lambda document: _cosine(
                query_vector, document_vectors[document.document_id]
            ),
            reverse=True,
        )[:k]
        cross_scope_candidates = [
            document.document_id
            for document in global_ranked
            if document.tenant_id != query.tenant_id
            or document.incident_id != query.incident_id
        ]
        if cross_scope_candidates:
            exposure_queries += 1
        query_reports.append(
            {
                "query_id": query.query_id,
                "variant": query.variant,
                "recall_at_k": recalls[str(k)],
                "recall_by_k": recalls,
                "returned_document_ids": returned,
                "cross_scope_leaks": leaks,
                "unscoped_collision_count": len(cross_scope_candidates),
                "latency_ms": round(elapsed_ms, 3),
            }
        )

    return {
        "model": embedder.model_id,
        "dimensions": embedder.dimensions,
        "k": k,
        "recall_cutoffs": cutoffs,
        "query_count": len(queries),
        "mean_recall_at_k": total_recall[k] / len(queries),
        "mean_recall_by_k": {
            str(cutoff): total_recall[cutoff] / len(queries)
            for cutoff in cutoffs
        },
        "cross_scope_leakage_rate": (
            leaked_documents / returned_documents if returned_documents else 0.0
        ),
        "cross_scope_leaked_documents": leaked_documents,
        "unscoped_collision_query_count": exposure_queries,
        "unscoped_collision_query_rate": exposure_queries / len(queries),
        "latency_ms": summarize_latency_ms(latency_samples),
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
    parser.add_argument("--region", default="ap-northeast-2")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument(
        "--ks",
        default="1,3,5",
        help="Comma-separated Recall@K cutoffs; --k is always included.",
    )
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
        ks=[int(value) for value in args.ks.split(",") if value],
    )
    assert_competition_gate(report, minimum_recall=args.minimum_recall)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

"""Credential-free, synthetic-only judge story over the live memory boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import Lock
import time
from typing import Any, Callable, Protocol

from continuum.identity import CallerIdentity, bind_caller


STORY_ID = "checkout-cache-pressure-v1"
STORY_MEMORY_KEY = "judge-checkout-cache-pressure-v1"
POISON_MEMORY_KEY = "judge-disable-verification-v1"
ACTION_KEY = "judge-restart-checkout-v1"
STORY_TITLE = "Checkout cache-pressure recovery"
STORY_QUERY = (
    "Checkout requests are timing out after cache connections saturated. "
    "What previously verified recovery should the incident agent use?"
)


class StoryKnowledgeService(Protocol):
    def search(self, query: str) -> Any: ...

    def fetch(self, memory_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class JudgeStoryService:
    """Replay one bounded incident story using live Titan and CockroachDB."""

    knowledge: StoryKnowledgeService
    identity: CallerIdentity
    connect: Callable[[], Any]

    def run(self, scenario: str) -> dict[str, Any]:
        if scenario != STORY_ID:
            raise ValueError("unknown judge scenario")

        with bind_caller(self.identity):
            search = self.knowledge.search(STORY_QUERY)
            selected = next(
                (result for result in search.results if result.title == STORY_TITLE),
                None,
            )
            if selected is None:
                raise RuntimeError("verified story memory was not retrieved")
            memory = self.knowledge.fetch(selected.id)

        with self.connect() as connection:
            accepted = connection.execute(
                """
                SELECT c.candidate_id::STRING, c.decision_code,
                       m.memory_id::STRING, m.sequence_no,
                       m.embedding_model
                FROM memory_candidates AS c
                JOIN canonical_memories AS m
                  ON m.source_candidate_id = c.candidate_id
                WHERE c.payload->>'judge_story_id' = %s
                  AND c.decision_code = 'ACCEPTED'
                ORDER BY m.accepted_at DESC
                LIMIT 1
                """,
                (STORY_MEMORY_KEY,),
            ).fetchone()
            rejected = connection.execute(
                """
                SELECT candidate_id::STRING, decision_code
                FROM memory_candidates
                WHERE payload->>'judge_story_id' = %s
                ORDER BY decided_at DESC
                LIMIT 1
                """,
                (POISON_MEMORY_KEY,),
            ).fetchone()
            action = connection.execute(
                """
                SELECT attempt_id::STRING, worker_id, status, expected_head,
                       (
                           SELECT count(*)
                           FROM action_attempts AS sibling
                           WHERE sibling.action_payload->>'judge_story_id' = %s
                             AND sibling.expected_head = latest.expected_head
                       )
                FROM action_attempts AS latest
                WHERE latest.action_payload->>'judge_story_id' = %s
                ORDER BY latest.created_at DESC
                LIMIT 1
                """,
                (STORY_ID, STORY_ID),
            ).fetchone()
            audit = connection.execute(
                """
                SELECT retrieval_id::STRING, embedding_model,
                       array_length(returned_memory_ids, 1),
                       array_length(accepted_memory_ids, 1)
                FROM retrieval_audit
                WHERE query_digest = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (hashlib.sha256(STORY_QUERY.encode("utf-8")).hexdigest(),),
            ).fetchone()

        if accepted is None or rejected is None or action is None or audit is None:
            raise RuntimeError("judge story receipts are incomplete")
        if rejected[1] != "UNTRUSTED_SOURCE" or int(action[4]) != 1:
            raise RuntimeError("judge story fail-closed contract is incomplete")

        return {
            "ok": True,
            "live": True,
            "scenario": STORY_ID,
            "persona": "on-call incident agent",
            "problem": "checkout timeouts after cache-connection saturation",
            "storage": {
                "candidate_id": accepted[0],
                "decision": accepted[1],
                "memory_id": accepted[2],
                "sequence_no": int(accepted[3]),
                "embedding_model": accepted[4],
            },
            "poisoning": {
                "candidate_id": rejected[0],
                "decision": rejected[1],
                "attempted_instruction": "disable payment verification",
            },
            "retrieval": {
                "query": STORY_QUERY,
                "selected": {
                    "id": memory.id,
                    "title": memory.title,
                    "text": memory.text,
                    "url": memory.url,
                    "metadata": memory.metadata,
                },
                "result_count": len(search.results),
                "audit_id": audit[0],
                "embedding_model": audit[1],
                "returned_count": int(audit[2] or 0),
                "accepted_count": int(audit[3] or 0),
            },
            "action": {
                "attempt_id": action[0],
                "worker_a": "CLAIMED",
                "worker_b": "DUPLICATE",
                "owner_worker_id": action[1],
                "status": action[2],
                "expected_head_prefix": str(action[3])[:12],
                "durable_claim_count": int(action[4]),
            },
            "authority": {
                "caller_fingerprint": hashlib.sha256(
                    self.identity.caller_id.encode("utf-8")
                ).hexdigest()[:12],
                "binding_version": self.identity.binding_version,
                "sql_role_fingerprint": hashlib.sha256(
                    (self.identity.sql_role or "").encode("utf-8")
                ).hexdigest()[:12],
                "tenant_and_incident_server_owned": True,
                "database_rls_enforced": True,
            },
        }


class CachedJudgeStoryEndpoint:
    """Bound the public Bedrock call rate while preserving a one-click demo."""

    def __init__(
        self,
        service: JudgeStoryService,
        *,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("judge story cache TTL must be at least one second")
        self._service = service
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._cached_at = 0.0
        self._cached: dict[str, Any] | None = None

    def run(self, scenario: str) -> tuple[dict[str, Any], bool]:
        with self._lock:
            now = self._clock()
            cached = self._cached
            if cached is not None and now - self._cached_at < self._ttl_seconds:
                return cached, True
            result = self._service.run(scenario)
            self._cached = result
            self._cached_at = now
            return result, False

"""Bounded Bedrock tool-calling orchestration for Continuum episodes.

Bedrock requests client-side tool use; this module executes only scoped memory
reads.  ``propose_action`` is a durable proposal, not an external side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from continuum.episode import (
    AgentArm,
    AgentRun,
    EpisodeStore,
    ProposedAction,
    RetrievedCitation,
    RiskClass,
)


MAX_MODEL_TURNS = 8
MAX_TOOL_CALLS = 16
MAX_QUERY_CHARS = 2_048
MAX_TOOL_RESULT_BYTES = 24 * 1024


SYSTEM_PROMPT = """You are a bounded incident-response planning agent.
You may search and fetch memory only through the supplied tools. Tenant and
incident scope are owned by the server and are never caller-selectable. You may
finish only by calling propose_action. A proposal is not execution. Cite every
memory that materially supports a non-stateless proposal. Never invent a
provider receipt or claim that an action succeeded."""


class OrchestrationError(RuntimeError):
    """Raised when a model violates the bounded tool contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        model_turns: int = 0,
        tool_calls: int = 0,
    ) -> None:
        super().__init__(message)
        normalized = re.sub(r"[^A-Z0-9]+", "_", message.upper()).strip("_")
        self.code = code or f"ORCHESTRATION_{normalized[:64]}"
        self.model_turns = model_turns
        self.tool_calls = tool_calls

    def attach_progress(self, *, model_turns: int, tool_calls: int) -> None:
        """Attach bounded counters without exposing provider exception text."""

        self.model_turns = max(self.model_turns, model_turns)
        self.tool_calls = max(self.tool_calls, tool_calls)


@dataclass(frozen=True, slots=True)
class MemoryToolHit:
    memory_id: str
    payload: Mapping[str, Any]
    similarity: float | None = None
    retrieval_id: str | None = None


class ScopedMemoryTools(Protocol):
    def search(self, *, query: str, limit: int) -> Sequence[MemoryToolHit]: ...

    def fetch(self, *, memory_id: str) -> MemoryToolHit: ...


class BedrockRuntime(Protocol):
    def converse(self, **kwargs: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    action_type: str
    risk_class: RiskClass
    allowed_parameters: frozenset[str]
    required_parameters: frozenset[str] = frozenset()

    def validate_parameters(self, value: object) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise OrchestrationError("action parameters must be an object")
        keys = {str(key) for key in value}
        if keys - self.allowed_parameters:
            raise OrchestrationError("action proposal contains forbidden parameters")
        if not self.required_parameters.issubset(keys):
            raise OrchestrationError("action proposal is missing required parameters")
        try:
            encoded = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OrchestrationError("action parameters are not valid JSON") from exc
        if len(encoded) > 16 * 1024:
            raise OrchestrationError("action parameters exceed 16 KiB")
        return dict(value)


DEFAULT_ACTION_POLICIES: Mapping[str, ActionPolicy] = {
    "restart_service": ActionPolicy(
        action_type="restart_service",
        risk_class=RiskClass.REVERSIBLE,
        allowed_parameters=frozenset({"service", "reason", "max_unavailable"}),
        required_parameters=frozenset({"service"}),
    ),
    "invalidate_cache": ActionPolicy(
        action_type="invalidate_cache",
        risk_class=RiskClass.REVERSIBLE,
        allowed_parameters=frozenset({"cache", "scope", "reason"}),
        required_parameters=frozenset({"cache"}),
    ),
    "inspect_service": ActionPolicy(
        action_type="inspect_service",
        risk_class=RiskClass.READ_ONLY,
        allowed_parameters=frozenset({"service", "check"}),
        required_parameters=frozenset({"service"}),
    ),
}


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    run: AgentRun
    proposal_id: str | None
    proposal: ProposedAction | None
    citations: tuple[RetrievedCitation, ...]
    model_turns: int
    tool_calls: int


class BedrockConverseClient:
    """Small injectable adapter around ``bedrock-runtime.converse``."""

    def __init__(
        self,
        *,
        region: str,
        runtime: BedrockRuntime | None = None,
    ) -> None:
        if runtime is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - optional boundary
                raise RuntimeError("install boto3 to use Bedrock orchestration") from exc
            runtime = boto3.client("bedrock-runtime", region_name=region)
        self._runtime = runtime

    def converse(self, **kwargs: Any) -> Mapping[str, Any]:
        return self._runtime.converse(**kwargs)


class AgentOrchestrator:
    """Run one bounded episode without granting model execution authority."""

    def __init__(
        self,
        *,
        store: EpisodeStore,
        model: BedrockRuntime,
        model_id: str,
        action_policies: Mapping[str, ActionPolicy] = DEFAULT_ACTION_POLICIES,
        max_model_turns: int = MAX_MODEL_TURNS,
        max_tool_calls: int = MAX_TOOL_CALLS,
    ) -> None:
        if max_model_turns < 1 or max_tool_calls < 1:
            raise ValueError("model and tool limits must be positive")
        self._store = store
        self._model = model
        self._model_id = model_id
        self._action_policies = dict(action_policies)
        if not self._action_policies:
            raise ValueError("at least one action policy is required")
        self._max_model_turns = max_model_turns
        self._max_tool_calls = max_tool_calls

    def run(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        arm: AgentArm,
        incident: Mapping[str, Any],
        memory_tools: ScopedMemoryTools | None,
    ) -> OrchestrationResult:
        if arm is AgentArm.STATELESS and memory_tools is not None:
            raise ValueError("stateless arm must not receive memory tools")
        if arm is not AgentArm.STATELESS and memory_tools is None:
            raise ValueError("memory-enabled arms require scoped memory tools")
        run = self._store.start_run(
            tenant_id=tenant_id,
            incident_id=incident_id,
            arm=arm,
            model_id=self._model_id,
            input_payload=incident,
        )
        try:
            return self._run_started(
                run=run,
                arm=arm,
                incident=incident,
                memory_tools=memory_tools,
            )
        except Exception:
            try:
                self._store.finish_without_action(
                    run=run,
                    final_text="orchestration rejected or failed",
                )
            except RuntimeError:
                # A proposal or terminal record may already own the transition.
                pass
            raise

    def _run_started(
        self,
        *,
        run: AgentRun,
        arm: AgentArm,
        incident: Mapping[str, Any],
        memory_tools: ScopedMemoryTools | None,
    ) -> OrchestrationResult:
        progress = {"model_turns": 0, "tool_calls": 0}
        try:
            return self._run_started_bounded(
                run=run,
                arm=arm,
                incident=incident,
                memory_tools=memory_tools,
                progress=progress,
            )
        except OrchestrationError as exc:
            exc.attach_progress(
                model_turns=progress["model_turns"],
                tool_calls=progress["tool_calls"],
            )
            raise

    def _run_started_bounded(
        self,
        *,
        run: AgentRun,
        arm: AgentArm,
        incident: Mapping[str, Any],
        memory_tools: ScopedMemoryTools | None,
        progress: dict[str, int],
    ) -> OrchestrationResult:
        input_text = json.dumps(
            incident,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        messages: list[Mapping[str, Any]] = [
            {"role": "user", "content": [{"text": input_text}]}
        ]
        citations: dict[str, RetrievedCitation] = {}
        tool_calls = 0
        search_attempted = False
        fetch_performed = False

        for model_turn in range(1, self._max_model_turns + 1):
            progress["model_turns"] = model_turn
            tool_specs = self._tool_specs(
                arm,
                search_attempted=search_attempted,
                has_search_hits=bool(citations),
                fetch_performed=fetch_performed,
            )
            allowed_tools = {
                str(item["toolSpec"]["name"]) for item in tool_specs
            }
            try:
                response = self._model.converse(
                    modelId=self._model_id,
                    system=[{"text": SYSTEM_PROMPT}],
                    messages=messages,
                    toolConfig={
                        "tools": tool_specs,
                        "toolChoice": {"any": {}},
                    },
                    inferenceConfig={
                        "maxTokens": 768,
                        "temperature": 0,
                        "topP": 0.9,
                    },
                    requestMetadata={
                        "continuum_arm": arm.value,
                        "continuum_run": run.run_id,
                    },
                )
            except OrchestrationError:
                raise
            except Exception as exc:
                raise OrchestrationError(
                    "Bedrock model invocation failed",
                    code="BEDROCK_MODEL_INVOCATION_FAILED",
                ) from exc

            output = response.get("output")
            if not isinstance(output, Mapping):
                raise OrchestrationError("Bedrock response has no output")
            message = output.get("message")
            if not isinstance(message, Mapping):
                raise OrchestrationError("Bedrock response has no message")
            messages.append(message)
            content = message.get("content")
            if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
                raise OrchestrationError("Bedrock message content is invalid")

            tool_result_blocks: list[Mapping[str, Any]] = []
            terminal: ProposedAction | None = None
            for block in content:
                if not isinstance(block, Mapping) or "toolUse" not in block:
                    continue
                tool_calls += 1
                progress["tool_calls"] = tool_calls
                if tool_calls > self._max_tool_calls:
                    raise OrchestrationError("tool-call budget exceeded")
                tool_use = block["toolUse"]
                if not isinstance(tool_use, Mapping):
                    raise OrchestrationError("toolUse block is invalid")
                tool_use_id = tool_use.get("toolUseId")
                name = tool_use.get("name")
                tool_input = tool_use.get("input", {})
                if not isinstance(tool_use_id, str) or not isinstance(name, str):
                    raise OrchestrationError("toolUse identity is invalid")
                if not isinstance(tool_input, Mapping):
                    raise OrchestrationError("tool input must be an object")
                if name not in allowed_tools:
                    raise OrchestrationError(
                        "model requested a tool outside the current episode phase"
                    )

                if name == "search_memory":
                    if memory_tools is None:
                        raise OrchestrationError("stateless arm requested memory search")
                    if search_attempted:
                        raise OrchestrationError("memory search may run only once")
                    result = self._search(memory_tools, tool_input, citations)
                    search_attempted = True
                    tool_result_blocks.append(
                        self._tool_result(tool_use_id, {"hits": result})
                    )
                elif name == "fetch_memory":
                    if memory_tools is None:
                        raise OrchestrationError("stateless arm requested memory fetch")
                    if fetch_performed:
                        raise OrchestrationError("memory fetch may run only once")
                    result = self._fetch(memory_tools, tool_input, citations)
                    fetch_performed = True
                    tool_result_blocks.append(self._tool_result(tool_use_id, result))
                elif name == "propose_action":
                    if terminal is not None:
                        raise OrchestrationError("model proposed more than one action")
                    terminal = self._proposal(
                        arm,
                        tool_input,
                        citations,
                        search_attempted=search_attempted,
                    )
                else:
                    raise OrchestrationError("model requested a forbidden tool")

            if terminal is not None:
                durable_citations = tuple(
                    sorted(citations.values(), key=lambda item: item.rank)
                )
                self._store.record_citations(run=run, citations=durable_citations)
                proposal_id = self._store.record_proposal(
                    run=run,
                    proposal=terminal,
                )
                return OrchestrationResult(
                    run=run,
                    proposal_id=proposal_id,
                    proposal=terminal,
                    citations=durable_citations,
                    model_turns=model_turn,
                    tool_calls=tool_calls,
                )

            if not tool_result_blocks:
                text = "\n".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, Mapping) and "text" in block
                )
                self._store.finish_without_action(run=run, final_text=text)
                return OrchestrationResult(
                    run=run,
                    proposal_id=None,
                    proposal=None,
                    citations=tuple(citations.values()),
                    model_turns=model_turn,
                    tool_calls=tool_calls,
                )
            messages.append({"role": "user", "content": tool_result_blocks})

        self._store.finish_without_action(
            run=run,
            final_text="model turn budget exhausted",
        )
        raise OrchestrationError("model turn budget exceeded")

    def _tool_specs(
        self,
        arm: AgentArm,
        *,
        search_attempted: bool,
        has_search_hits: bool,
        fetch_performed: bool,
    ) -> list[Mapping[str, Any]]:
        propose_tool: Mapping[str, Any] = {
            "toolSpec": {
                "name": "propose_action",
                "description": "Propose, but never execute, one allowlisted action.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "action_key": {"type": "string"},
                            "action_type": {
                                "type": "string",
                                "enum": sorted(self._action_policies),
                            },
                            "parameters": {"type": "object"},
                            "rationale": {"type": "string"},
                            "citation_memory_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 20,
                            },
                        },
                        "required": [
                            "action_key",
                            "action_type",
                            "parameters",
                            "rationale",
                            "citation_memory_ids",
                        ],
                        "additionalProperties": False,
                    }
                },
            }
        }
        if arm is AgentArm.STATELESS:
            return [propose_tool]
        if not search_attempted:
            return [
                {
                    "toolSpec": {
                        "name": "search_memory",
                        "description": "Search server-scoped incident memory.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "limit": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 5,
                                    },
                                },
                                "required": ["query"],
                                "additionalProperties": False,
                            },
                        },
                    }
                }
            ]
        tools: list[Mapping[str, Any]] = []
        if has_search_hits and not fetch_performed:
            tools.append(
                {
                    "toolSpec": {
                        "name": "fetch_memory",
                        "description": "Fetch one memory returned by scoped search.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {"memory_id": {"type": "string"}},
                                "required": ["memory_id"],
                                "additionalProperties": False,
                            },
                        },
                    }
                }
            )
        tools.append(propose_tool)
        return tools

    def _search(
        self,
        memory_tools: ScopedMemoryTools,
        value: Mapping[str, Any],
        citations: dict[str, RetrievedCitation],
    ) -> list[Mapping[str, Any]]:
        if set(value) - {"query", "limit"}:
            raise OrchestrationError("search contains forbidden fields")
        query = value.get("query")
        limit = value.get("limit", 5)
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise OrchestrationError("search query is invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5:
            raise OrchestrationError("search limit is invalid")
        hits = tuple(memory_tools.search(query=query.strip(), limit=limit))
        result: list[Mapping[str, Any]] = []
        for hit in hits[:limit]:
            rank = len(citations) + 1
            citation = citations.get(hit.memory_id)
            if citation is None:
                citation = RetrievedCitation(
                    memory_id=hit.memory_id,
                    rank=rank,
                    payload=dict(hit.payload),
                    similarity=hit.similarity,
                    retrieval_id=hit.retrieval_id,
                )
                citations[hit.memory_id] = citation
            result.append(self._public_hit(citation))
        self._bounded_tool_result({"hits": result})
        return result

    def _fetch(
        self,
        memory_tools: ScopedMemoryTools,
        value: Mapping[str, Any],
        citations: dict[str, RetrievedCitation],
    ) -> Mapping[str, Any]:
        if set(value) != {"memory_id"}:
            raise OrchestrationError("fetch accepts only memory_id")
        memory_id = value.get("memory_id")
        if not isinstance(memory_id, str) or memory_id not in citations:
            raise OrchestrationError("fetch may read only a prior search hit")
        hit = memory_tools.fetch(memory_id=memory_id)
        if hit.memory_id != memory_id:
            raise OrchestrationError("memory tool returned a mismatched identity")
        prior = citations[memory_id]
        citation = RetrievedCitation(
            memory_id=memory_id,
            rank=prior.rank,
            payload=dict(hit.payload),
            similarity=prior.similarity,
            retrieval_id=prior.retrieval_id,
        )
        citations[memory_id] = citation
        result = self._public_hit(citation)
        self._bounded_tool_result(result)
        return result

    def _proposal(
        self,
        arm: AgentArm,
        value: Mapping[str, Any],
        citations: Mapping[str, RetrievedCitation],
        *,
        search_attempted: bool,
    ) -> ProposedAction:
        expected = {
            "action_key",
            "action_type",
            "parameters",
            "rationale",
            "citation_memory_ids",
        }
        if set(value) != expected:
            raise OrchestrationError("action proposal fields do not match contract")
        action_type = value.get("action_type")
        if not isinstance(action_type, str) or action_type not in self._action_policies:
            raise OrchestrationError("action type is not allowlisted")
        action_key = value.get("action_key")
        rationale = value.get("rationale")
        cited = value.get("citation_memory_ids")
        if not isinstance(action_key, str) or not action_key.strip():
            raise OrchestrationError("action_key is required")
        if not isinstance(rationale, str) or not rationale.strip():
            raise OrchestrationError("action rationale is required")
        if not isinstance(cited, Sequence) or isinstance(cited, (str, bytes)):
            raise OrchestrationError("citation_memory_ids must be an array")
        cited_ids = tuple(cited)
        if not all(isinstance(item, str) for item in cited_ids):
            raise OrchestrationError("citation memory IDs must be strings")
        if arm is not AgentArm.STATELESS and not search_attempted:
            raise OrchestrationError("memory-enabled proposal must search first")
        if arm is not AgentArm.STATELESS and citations and not cited_ids:
            raise OrchestrationError("memory-enabled proposal must cite memory")
        if arm is AgentArm.STATELESS and cited_ids:
            raise OrchestrationError("stateless proposal cannot cite memory")
        if not set(cited_ids).issubset(citations):
            raise OrchestrationError("proposal cites memory not returned by search")
        policy = self._action_policies[action_type]
        parameters = policy.validate_parameters(value.get("parameters"))
        return ProposedAction(
            action_key=action_key.strip(),
            action_type=action_type,
            parameters=parameters,
            rationale=rationale.strip(),
            citation_memory_ids=cited_ids,
            risk_class=policy.risk_class,
        )

    @staticmethod
    def _public_hit(citation: RetrievedCitation) -> Mapping[str, Any]:
        return {
            "memory_id": citation.memory_id,
            "rank": citation.rank,
            "similarity": citation.similarity,
            "payload": dict(citation.payload),
        }

    @staticmethod
    def _tool_result(tool_use_id: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
        AgentOrchestrator._bounded_tool_result(value)
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"json": dict(value)}],
                "status": "success",
            }
        }

    @staticmethod
    def _bounded_tool_result(value: Mapping[str, Any]) -> None:
        try:
            encoded = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OrchestrationError("memory tool returned invalid JSON") from exc
        if len(encoded) > MAX_TOOL_RESULT_BYTES:
            raise OrchestrationError("memory tool result exceeds 24 KiB")


class RetrievalStoreTools:
    """Bind server-owned scope around the existing vector retrieval store."""

    def __init__(
        self,
        *,
        store: Any,
        embedder: Any,
        tenant_id: str,
        incident_id: str,
        min_similarity: float = 0.05,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._tenant_id = tenant_id
        self._incident_id = incident_id
        self._min_similarity = min_similarity

    def search(self, *, query: str, limit: int) -> Sequence[MemoryToolHit]:
        result = self._store.search(
            tenant_id=self._tenant_id,
            incident_id=self._incident_id,
            query=query,
            embedder=self._embedder,
            limit=limit,
            min_similarity=self._min_similarity,
        )
        return tuple(
            MemoryToolHit(
                memory_id=hit.memory_id,
                payload=hit.payload,
                similarity=hit.similarity,
                retrieval_id=result.retrieval_id,
            )
            for hit in result.hits
        )

    def fetch(self, *, memory_id: str) -> MemoryToolHit:
        document = self._store.fetch_memory(
            tenant_id=self._tenant_id,
            incident_id=self._incident_id,
            memory_id=memory_id,
        )
        return MemoryToolHit(
            memory_id=document.memory_id,
            payload=document.payload,
        )

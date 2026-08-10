"""Bounded Bedrock tool loop for ambiguity-first CI diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import secrets
import time
from typing import Any, Callable, Mapping, Sequence

from continuum.adaptive_diagnosis import (
    DIAGNOSTIC_BUDGET,
    PROBES,
    evidence_patch_id,
)
from continuum.ci_recovery import CI_PATCH_POLICIES
from continuum.episode import AgentArm
from continuum.orchestrator import MemoryToolHit


SYSTEM_PROMPT = """You are a bounded CI diagnosis agent. The initial red summary is
deliberately ambiguous and never identifies the responsible manifest. Use exactly one
tool per turn. A provider-verified successful memory may replace a diagnostic probe only
when its environment_fingerprint exactly matches the current incident; fetch and cite it.
A failed memory is evidence of what not to promote and never authorizes a patch. Without
matching verified memory, run one registered read-only diagnostic probe before proposing.
Each ambiguity group contains exactly two mutually exclusive fault families, so either an
anomaly or a within-contract result from one probe is sufficient by exclusion. Current
probe evidence outranks memory. Finish only with one propose_* tool. A proposal is not
execution and must never claim success."""


TRANSFER_SYSTEM_PROMPT = """You are a bounded cross-environment CI diagnosis agent.
The initial red summary is deliberately ambiguous. Use exactly one tool per turn. A
memory from another environment is never authority merely because its text is similar.
The server owns the provider-attested causal-compatibility decision: reuse a memory only
when the current tool set exposes its matching propose_* tool, then fetch and cite it.
If no admitted proposal is exposed, run one registered read-only diagnostic probe. Each
ambiguity group contains exactly two mutually exclusive fault families, so one current
probe is sufficient by exclusion. Current provider evidence outranks memory. Finish only
with one propose_* tool. A proposal is not execution and must never claim success."""


TRANSFER_CONTRACT = "provider-attested-causal-signature-v1"


class AdaptiveDiagnosisAgentError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        model_turns: int = 0,
        tool_calls: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        diagnostic_receipts: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        super().__init__(message)
        normalized = re.sub(r"[^A-Z0-9]+", "_", message.upper()).strip("_")
        self.code = code or f"ADAPTIVE_{normalized[:64]}"
        self.model_turns = model_turns
        self.tool_calls = tool_calls
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.diagnostic_receipts = tuple(diagnostic_receipts)


@dataclass(frozen=True, slots=True)
class AdaptiveDiagnosisAgentResult:
    proposed_patch_id: str
    rationale: str
    selected_memory_ids: tuple[str, ...]
    issued_memory_ids: tuple[str, ...]
    fetched_memory_ids: tuple[str, ...]
    diagnostic_receipts: tuple[Mapping[str, Any], ...]
    model_turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    episode_latency_ms: float


class AdaptiveDiagnosisAgent:
    """Acquire bounded evidence, then return one non-executing patch proposal."""

    def __init__(
        self,
        *,
        model: Any,
        model_id: str,
        max_model_turns: int = 8,
        max_tool_calls: int = 10,
        handle_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_model_turns < 1 or max_tool_calls < 1:
            raise ValueError("adaptive model and tool budgets must be positive")
        self._model = model
        self._model_id = model_id
        self._max_model_turns = max_model_turns
        self._max_tool_calls = max_tool_calls
        self._handle_factory = handle_factory or (
            lambda: f"cit_{secrets.token_urlsafe(18)}"
        )

    def run(
        self,
        *,
        arm: AgentArm,
        incident: Mapping[str, Any],
        memory_hits: Sequence[MemoryToolHit],
        run_probe: Callable[[str], Mapping[str, Any]],
        request_metadata: Mapping[str, str] | None = None,
    ) -> AdaptiveDiagnosisAgentResult:
        if arm is AgentArm.STATELESS and memory_hits:
            raise ValueError("stateless adaptive arm cannot receive memory")
        allowed_probes = incident.get("allowed_probe_ids")
        if (
            not isinstance(allowed_probes, Sequence)
            or isinstance(allowed_probes, (str, bytes))
            or len(allowed_probes) != 2
            or not all(item in PROBES for item in allowed_probes)
        ):
            raise ValueError("adaptive incident probe pair is invalid")
        if incident.get("diagnostic_budget") != DIAGNOSTIC_BUDGET:
            raise ValueError("adaptive incident diagnostic budget drifted")
        fingerprint = str(incident.get("environment_fingerprint", ""))
        if re.fullmatch(r"env-[0-9a-f]{20}", fingerprint) is None:
            raise ValueError("adaptive incident fingerprint is invalid")
        transfer_contract = incident.get("transfer_contract")
        if transfer_contract is not None and transfer_contract != TRANSFER_CONTRACT:
            raise ValueError("adaptive transfer contract is invalid")

        started_ns = time.perf_counter_ns()
        messages: list[Mapping[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "text": json.dumps(
                            incident,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    }
                ],
            }
        ]
        searched = arm is AgentArm.STATELESS
        handles: dict[str, MemoryToolHit] = {}
        fetched_handles: list[str] = []
        diagnostic_receipts: list[Mapping[str, Any]] = []
        used_probes: set[str] = set()
        tool_calls = 0
        input_tokens = 0
        output_tokens = 0

        try:
            for model_turn in range(1, self._max_model_turns + 1):
                tools = self._tool_specs(
                    arm=arm,
                    searched=searched,
                    handles=handles,
                    fetched_handles=fetched_handles,
                    environment_fingerprint=fingerprint,
                    transfer_contract=(
                        str(transfer_contract) if transfer_contract is not None else None
                    ),
                    allowed_probes=tuple(str(item) for item in allowed_probes),
                    used_probes=used_probes,
                    diagnostic_receipts=diagnostic_receipts,
                )
                try:
                    response = self._model.converse(
                        modelId=self._model_id,
                        system=[
                            {
                                "text": (
                                    TRANSFER_SYSTEM_PROMPT
                                    if transfer_contract is not None
                                    else SYSTEM_PROMPT
                                )
                            }
                        ],
                        messages=messages,
                        toolConfig={"tools": tools, "toolChoice": {"any": {}}},
                        inferenceConfig={
                            "maxTokens": 900,
                            "temperature": 0,
                            "topP": 0.9,
                        },
                        requestMetadata=self._metadata(
                            arm=arm,
                            incident=incident,
                            extra=request_metadata,
                        ),
                    )
                except Exception as exc:
                    raise AdaptiveDiagnosisAgentError(
                        "Bedrock model invocation failed",
                        code="ADAPTIVE_BEDROCK_MODEL_INVOCATION_FAILED",
                    ) from exc
                usage = response.get("usage", {})
                if isinstance(usage, Mapping):
                    input_tokens += int(usage.get("inputTokens", 0) or 0)
                    output_tokens += int(usage.get("outputTokens", 0) or 0)
                output = response.get("output")
                message = output.get("message") if isinstance(output, Mapping) else None
                if not isinstance(message, Mapping):
                    raise AdaptiveDiagnosisAgentError("Bedrock response has no message")
                messages.append(message)
                content = message.get("content")
                if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
                    raise AdaptiveDiagnosisAgentError(
                        "Bedrock adaptive message content is invalid"
                    )
                tool_uses = [
                    block["toolUse"]
                    for block in content
                    if isinstance(block, Mapping)
                    and isinstance(block.get("toolUse"), Mapping)
                ]
                if len(tool_uses) != 1:
                    raise AdaptiveDiagnosisAgentError(
                        "adaptive model must call exactly one tool per turn"
                    )
                tool_calls += 1
                if tool_calls > self._max_tool_calls:
                    raise AdaptiveDiagnosisAgentError("adaptive tool-call budget exceeded")
                tool_use = tool_uses[0]
                tool_use_id = tool_use.get("toolUseId")
                name = tool_use.get("name")
                value = tool_use.get("input", {})
                if (
                    not isinstance(tool_use_id, str)
                    or not isinstance(name, str)
                    or not isinstance(value, Mapping)
                ):
                    raise AdaptiveDiagnosisAgentError("adaptive tool use is malformed")
                allowed_names = {
                    str(item["toolSpec"]["name"]) for item in tools
                }
                if name not in allowed_names:
                    raise AdaptiveDiagnosisAgentError(
                        "adaptive model requested a tool outside the current phase"
                    )

                if name == "search_memory":
                    if searched or arm is AgentArm.STATELESS:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive memory search is not available"
                        )
                    searched = True
                    limit = value.get("limit", 5)
                    query = value.get("query")
                    if (
                        not isinstance(query, str)
                        or not query.strip()
                        or not isinstance(limit, int)
                        or isinstance(limit, bool)
                        or not 1 <= limit <= 5
                    ):
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive memory search input is invalid"
                        )
                    public_hits = []
                    for hit in tuple(memory_hits)[:limit]:
                        handle = self._new_handle(handles)
                        handles[handle] = hit
                        public_hits.append(
                            {
                                "citation_handle": handle,
                                "similarity": hit.similarity,
                                "provider_conclusion": hit.payload.get(
                                    "provider_conclusion"
                                ),
                                "environment_fingerprint": hit.payload.get(
                                    "environment_fingerprint"
                                ),
                                "summary": hit.payload.get("summary"),
                            }
                        )
                    messages.append(
                        self._tool_result(tool_use_id, {"hits": public_hits})
                    )
                    continue

                if name == "fetch_memory":
                    handle = value.get("citation_handle")
                    if set(value) != {"citation_handle"} or handle not in handles:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive fetch handle was not issued by search"
                        )
                    if handle in fetched_handles:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive memory handle was fetched twice"
                        )
                    fetched_handles.append(str(handle))
                    hit = handles[str(handle)]
                    messages.append(
                        self._tool_result(
                            tool_use_id,
                            {
                                "citation_handle": handle,
                                "memory": dict(hit.payload),
                            },
                        )
                    )
                    continue

                if name == "run_diagnostic_probe":
                    probe_id = value.get("probe_id")
                    if set(value) != {"probe_id"} or probe_id not in allowed_probes:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive diagnostic probe input is invalid"
                        )
                    if probe_id in used_probes:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive diagnostic probe was repeated"
                        )
                    if len(used_probes) >= DIAGNOSTIC_BUDGET:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive diagnostic budget exceeded"
                        )
                    receipt = run_probe(str(probe_id))
                    payload = receipt.get("provider_payload")
                    if (
                        receipt.get("conclusion") != "success"
                        or not isinstance(payload, Mapping)
                        or payload.get("kind")
                        != "continuum.adaptive-diagnosis.probe"
                        or payload.get("probe_id") != probe_id
                        or payload.get("read_only") is not True
                    ):
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive diagnostic provider receipt is invalid"
                        )
                    used_probes.add(str(probe_id))
                    diagnostic_receipts.append(receipt)
                    messages.append(
                        self._tool_result(
                            tool_use_id,
                            {
                                "probe_id": probe_id,
                                "finding": payload.get("finding"),
                                "facts": payload.get("facts"),
                                "provider_receipt": {
                                    "workflow_run_id": receipt.get("workflow_run_id"),
                                    "artifact_digest": receipt.get("artifact_digest"),
                                    "receipt_sha256": receipt.get("receipt_sha256"),
                                    "conclusion": receipt.get("conclusion"),
                                },
                            },
                        )
                    )
                    continue

                if name.startswith("propose_"):
                    proposed_patch_id = name.removeprefix("propose_")
                    policy = CI_PATCH_POLICIES.get(proposed_patch_id)
                    if policy is None:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive proposal tool is not reviewed"
                        )
                    expected_fields = {
                        "action_key",
                        "parameters",
                        "rationale",
                        "citation_handles",
                    }
                    if set(value) != expected_fields:
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive proposal fields do not match contract"
                        )
                    rationale = value.get("rationale")
                    action_key = value.get("action_key")
                    cited = value.get("citation_handles")
                    if (
                        not isinstance(action_key, str)
                        or not action_key.strip()
                        or not isinstance(rationale, str)
                        or not rationale.strip()
                        or not isinstance(cited, Sequence)
                        or isinstance(cited, (str, bytes))
                        or not all(isinstance(item, str) for item in cited)
                        or len(set(cited)) != len(cited)
                        or not set(cited).issubset(handles)
                    ):
                        raise AdaptiveDiagnosisAgentError(
                            "adaptive proposal evidence fields are invalid"
                        )
                    policy.validate_parameters(value.get("parameters"))
                    admissible_citations = {
                        handle
                        for handle in cited
                        if handle in fetched_handles
                        and self._memory_authorizes_patch(
                            arm=arm,
                            hit=handles[handle],
                            environment_fingerprint=fingerprint,
                            transfer_contract=(
                                str(transfer_contract)
                                if transfer_contract is not None
                                else None
                            ),
                            patch_id=proposed_patch_id,
                        )
                    }
                    if set(cited) != admissible_citations:
                        messages.append(
                            self._tool_result(
                                tool_use_id,
                                {
                                    "error": (
                                        "citation handles must be fetched, server-admitted, "
                                        "and authorize the proposed patch"
                                    )
                                },
                                error=True,
                            )
                        )
                        continue
                    verified_support = bool(admissible_citations)
                    if not diagnostic_receipts and not verified_support:
                        messages.append(
                            self._tool_result(
                                tool_use_id,
                                {
                                    "error": (
                                        "proposal requires either a matching fetched "
                                        "provider-success memory or a read-only probe receipt"
                                    )
                                },
                                error=True,
                            )
                        )
                        continue
                    selected_memory_ids = tuple(
                        handles[handle].memory_id for handle in cited
                    )
                    return AdaptiveDiagnosisAgentResult(
                        proposed_patch_id=proposed_patch_id,
                        rationale=rationale.strip(),
                        selected_memory_ids=selected_memory_ids,
                        issued_memory_ids=tuple(
                            hit.memory_id for hit in handles.values()
                        ),
                        fetched_memory_ids=tuple(
                            handles[handle].memory_id for handle in fetched_handles
                        ),
                        diagnostic_receipts=tuple(diagnostic_receipts),
                        model_turns=model_turn,
                        tool_calls=tool_calls,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        episode_latency_ms=round(
                            (time.perf_counter_ns() - started_ns) / 1_000_000, 3
                        ),
                    )
                raise AdaptiveDiagnosisAgentError("adaptive tool route is invalid")
            raise AdaptiveDiagnosisAgentError("adaptive model turn budget exceeded")
        except AdaptiveDiagnosisAgentError as exc:
            exc.model_turns = max(exc.model_turns, locals().get("model_turn", 0))
            exc.tool_calls = max(exc.tool_calls, tool_calls)
            exc.input_tokens = max(exc.input_tokens, input_tokens)
            exc.output_tokens = max(exc.output_tokens, output_tokens)
            exc.diagnostic_receipts = tuple(diagnostic_receipts)
            raise

    def _tool_specs(
        self,
        *,
        arm: AgentArm,
        searched: bool,
        handles: Mapping[str, MemoryToolHit],
        fetched_handles: Sequence[str],
        environment_fingerprint: str,
        transfer_contract: str | None,
        allowed_probes: Sequence[str],
        used_probes: set[str],
        diagnostic_receipts: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        if arm is not AgentArm.STATELESS and not searched:
            return [
                {
                    "toolSpec": {
                        "name": "search_memory",
                        "description": (
                            (
                                "Search server-owned memory for provider-verified prior "
                                "outcomes. Cross-environment reuse remains server-gated."
                                if transfer_contract is not None
                                else "Search server-owned memory for this exact environment fingerprint."
                            )
                        ),
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
                            }
                        },
                    }
                }
            ]
        # A current provider fact outranks all memory. Compile it into a single
        # discriminated proposal schema, so the model cannot request a second
        # low-value probe or an action contradicted by the receipt.
        if diagnostic_receipts:
            payload = diagnostic_receipts[-1].get("provider_payload")
            if not isinstance(payload, Mapping):
                raise AdaptiveDiagnosisAgentError(
                    "adaptive diagnostic provider payload is invalid"
                )
            patch_id = evidence_patch_id(
                str(payload.get("probe_id", "")),
                str(payload.get("finding", "")),
            )
            return [
                self._proposal_tool(
                    CI_PATCH_POLICIES[patch_id],
                    (),
                    require_citation=False,
                )
            ]

        verified_handles = [
            handle
            for handle, hit in handles.items()
            if self._memory_authorizes_patch(
                arm=arm,
                hit=hit,
                environment_fingerprint=environment_fingerprint,
                transfer_contract=transfer_contract,
                patch_id=str(hit.payload.get("patch_id", "")),
            )
        ]
        # The raw-RAG comparator deliberately treats a provider-success source
        # memory as transferable based on retrieval alone. The evaluator scores
        # this baseline's near-neighbour failures; Continuum never takes this path.
        if (
            transfer_contract == TRANSFER_CONTRACT
            and arm is AgentArm.RAW_RAG
            and verified_handles
        ):
            fetched_verified = [
                handle for handle in verified_handles if handle in fetched_handles
            ]
            if not fetched_verified:
                return [self._fetch_tool(verified_handles)]
            patch_ids = {
                str(handles[handle].payload["patch_id"])
                for handle in fetched_verified
            }
            if len(patch_ids) != 1:
                raise AdaptiveDiagnosisAgentError(
                    "adaptive raw transfer memories disagree on a patch"
                )
            patch_id = next(iter(patch_ids))
            return [
                self._proposal_tool(
                    CI_PATCH_POLICIES[patch_id],
                    tuple(fetched_verified),
                    require_citation=True,
                )
            ]
        # Continuum's outcome gate is a control-plane decision, not a model
        # suggestion. Exact provider-success memory must be fetched, cited, and
        # routed to its matching proposal before any diagnostic probe is exposed.
        if arm is AgentArm.CONTINUUM and verified_handles:
            fetched_verified = [
                handle
                for handle in verified_handles
                if handle in fetched_handles
            ]
            if not fetched_verified:
                return [self._fetch_tool(verified_handles)]
            patch_ids = {
                str(handles[handle].payload["patch_id"])
                for handle in fetched_verified
            }
            if len(patch_ids) != 1:
                raise AdaptiveDiagnosisAgentError(
                    "adaptive verified memories disagree on a patch"
                )
            patch_id = next(iter(patch_ids))
            return [
                self._proposal_tool(
                    CI_PATCH_POLICIES[patch_id],
                    tuple(fetched_verified),
                    require_citation=True,
                )
            ]

        tools: list[Mapping[str, Any]] = []
        available_handles = [
            handle
            for handle in handles
            if handle not in fetched_handles
            and not (
                transfer_contract == TRANSFER_CONTRACT
                and arm is AgentArm.CONTINUUM
                and handle not in verified_handles
            )
        ]
        if available_handles:
            tools.append(self._fetch_tool(available_handles))
        available_probes = [
            probe_id for probe_id in allowed_probes if probe_id not in used_probes
        ]
        if not used_probes and available_probes:
            tools.append(
                {
                    "toolSpec": {
                        "name": "run_diagnostic_probe",
                        "description": (
                            "Run one actual read-only GitHub Actions probe. One result "
                            "is sufficient because the two fault families are exclusive."
                        ),
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "probe_id": {
                                        "type": "string",
                                        "enum": available_probes,
                                    }
                                },
                                "required": ["probe_id"],
                                "additionalProperties": False,
                            }
                        },
                    }
                }
            )
        supported: dict[str, list[str]] = {}
        for handle in fetched_handles:
            hit = handles[handle]
            patch_id = str(hit.payload.get("patch_id", ""))
            if self._memory_authorizes_patch(
                arm=arm,
                hit=hit,
                environment_fingerprint=environment_fingerprint,
                transfer_contract=transfer_contract,
                patch_id=patch_id,
            ):
                supported.setdefault(patch_id, []).append(handle)
        tools.extend(
            self._proposal_tool(
                CI_PATCH_POLICIES[patch_id],
                tuple(citation_handles),
                require_citation=True,
            )
            for patch_id, citation_handles in sorted(supported.items())
        )
        if not tools:
            raise AdaptiveDiagnosisAgentError(
                "adaptive evidence router has no admissible tool"
            )
        return tools

    @staticmethod
    def _memory_authorizes_patch(
        *,
        arm: AgentArm,
        hit: MemoryToolHit,
        environment_fingerprint: str,
        transfer_contract: str | None,
        patch_id: str,
    ) -> bool:
        payload = hit.payload
        if (
            payload.get("provider_conclusion") != "success"
            or payload.get("patch_id") != patch_id
            or patch_id not in CI_PATCH_POLICIES
        ):
            return False
        source_fingerprint = str(payload.get("environment_fingerprint", ""))
        if source_fingerprint == environment_fingerprint:
            return True
        if transfer_contract != TRANSFER_CONTRACT:
            return False
        if arm is AgentArm.RAW_RAG:
            return (
                re.fullmatch(r"env-[0-9a-f]{20}", source_fingerprint) is not None
                and source_fingerprint != environment_fingerprint
            )
        return (
            arm is AgentArm.CONTINUUM
            and payload.get("transfer_contract") == TRANSFER_CONTRACT
            and payload.get("transfer_compatible") is True
            and payload.get("source_environment_fingerprint")
            == source_fingerprint
            and payload.get("target_environment_fingerprint")
            == environment_fingerprint
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(payload.get("target_attestation_receipt_sha256", "")),
            )
            is not None
        )

    @staticmethod
    def _fetch_tool(handles: Sequence[str]) -> Mapping[str, Any]:
        return {
            "toolSpec": {
                "name": "fetch_memory",
                "description": (
                    "Fetch one handle returned by the current scoped search."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "citation_handle": {
                                "type": "string",
                                "enum": list(handles),
                            }
                        },
                        "required": ["citation_handle"],
                        "additionalProperties": False,
                    }
                },
            }
        }

    @staticmethod
    def _proposal_tool(
        policy: Any,
        handles: Sequence[str],
        *,
        require_citation: bool,
    ) -> Mapping[str, Any]:
        citation_item: dict[str, Any] = {"type": "string"}
        if handles:
            citation_item["enum"] = list(handles)
        citation_schema: dict[str, Any] = {
            "type": "array",
            "items": citation_item,
            "maxItems": len(handles),
            "uniqueItems": True,
        }
        if require_citation:
            citation_schema["minItems"] = 1
        return {
            "toolSpec": {
                "name": policy.tool_name,
                "description": (
                    f"Propose, never execute, {policy.action_type}. "
                    f"Selection rule: {policy.selection_rule}"
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "action_key": {"type": "string", "minLength": 1},
                            "parameters": policy.parameter_schema(),
                            "rationale": {"type": "string", "minLength": 1},
                            "citation_handles": citation_schema,
                        },
                        "required": [
                            "action_key",
                            "parameters",
                            "rationale",
                            "citation_handles",
                        ],
                        "additionalProperties": False,
                    }
                },
            }
        }

    @staticmethod
    def _tool_result(
        tool_use_id: str, value: Mapping[str, Any], *, error: bool = False
    ) -> Mapping[str, Any]:
        result: dict[str, Any] = {
            "toolUseId": tool_use_id,
            "content": [{"json": dict(value)}],
        }
        if error:
            result["status"] = "error"
        return {"role": "user", "content": [{"toolResult": result}]}

    def _new_handle(self, issued: Mapping[str, MemoryToolHit]) -> str:
        for _ in range(20):
            handle = self._handle_factory()
            if (
                isinstance(handle, str)
                and re.fullmatch(r"cit_[A-Za-z0-9_-]{8,96}", handle)
                and handle not in issued
            ):
                return handle
        raise AdaptiveDiagnosisAgentError("adaptive citation handle generation failed")

    @staticmethod
    def _metadata(
        *,
        arm: AgentArm,
        incident: Mapping[str, Any],
        extra: Mapping[str, str] | None,
    ) -> Mapping[str, str]:
        value = {
            "continuum_evaluation": "adaptive_diagnosis",
            "continuum_arm": arm.value,
            "continuum_case": str(incident["case_id"]),
        }
        if extra:
            for key, item in extra.items():
                if key in value or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) is None:
                    raise ValueError("adaptive request metadata key is invalid")
                if not isinstance(item, str) or len(item) > 256:
                    raise ValueError("adaptive request metadata value is invalid")
                value[key] = item
        return value

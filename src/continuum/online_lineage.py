"""Receipt-bound admission for online CockroachDB memory transfer.

The vector store decides which same-scope memories are visible.  This wrapper
then joins each provider-success source outcome to a separately verified target
attestation before the model sees an action-specific proposal tool.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Collection, Mapping, Sequence

from continuum.adaptive_diagnosis import ADAPTIVE_DIAGNOSIS_FAMILIES
from continuum.adaptive_diagnosis_agent import TRANSFER_CONTRACT
from continuum.ci_recovery import CI_PATCH_POLICIES, validate_ci_workflow_receipt
from continuum.episode import canonical_json_bytes
from continuum.orchestrator import MemoryToolHit, ScopedMemoryTools


class TransferAdmissionError(RuntimeError):
    """Raised when provider or database lineage cannot be joined safely."""


def family_for_patch(patch_id: str) -> str:
    """Resolve one reviewed patch to exactly one registered fault family."""

    matches = [
        family.family
        for family in ADAPTIVE_DIAGNOSIS_FAMILIES
        if family.expected_patch_id == patch_id
    ]
    if len(matches) != 1:
        raise RuntimeError("online lineage patch has no unique fault family")
    return matches[0]


@dataclass(frozen=True, slots=True)
class TransferAdmissionReceipt:
    target_environment_fingerprint: str
    target_causal_signature: str
    target_attestation_receipt_sha256: str
    target_workflow_run_id: int
    searched_memory_ids: tuple[str, ...]
    compatible_memory_ids: tuple[str, ...]
    retrieval_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "continuum.online-transfer-admission",
            "transfer_contract": TRANSFER_CONTRACT,
            "target_environment_fingerprint": self.target_environment_fingerprint,
            "target_causal_signature": self.target_causal_signature,
            "target_attestation_receipt_sha256": (
                self.target_attestation_receipt_sha256
            ),
            "target_workflow_run_id": self.target_workflow_run_id,
            "searched_memory_ids": list(self.searched_memory_ids),
            "compatible_memory_ids": list(self.compatible_memory_ids),
            "retrieval_ids": list(self.retrieval_ids),
        }


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _target_attestation(receipt: Mapping[str, Any]) -> Mapping[str, str]:
    validate_ci_workflow_receipt(receipt, expected_conclusion="success")
    payload = receipt.get("provider_payload")
    if not isinstance(payload, Mapping):
        raise TransferAdmissionError("target attestation payload is missing")
    required = {
        "causal_signature",
        "environment_fingerprint",
        "kind",
        "read_only",
        "transfer_contract",
        "workspace_sha256_after",
        "workspace_sha256_before",
    }
    if not required.issubset(payload):
        raise TransferAdmissionError("target attestation payload is incomplete")
    if (
        payload.get("kind") != "continuum.transfer-firewall.attestation"
        or payload.get("transfer_contract") != TRANSFER_CONTRACT
        or payload.get("read_only") is not True
        or payload.get("workspace_sha256_before")
        != payload.get("workspace_sha256_after")
    ):
        raise TransferAdmissionError("target attestation contract failed")
    fingerprint = str(payload.get("environment_fingerprint", ""))
    signature = str(payload.get("causal_signature", ""))
    receipt_sha = str(receipt.get("receipt_sha256", ""))
    if re.fullmatch(r"env-[0-9a-f]{20}", fingerprint) is None:
        raise TransferAdmissionError("target environment fingerprint is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", signature) is None:
        raise TransferAdmissionError("target causal signature is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", receipt_sha) is None:
        raise TransferAdmissionError("target attestation receipt digest is invalid")
    return {
        "environment_fingerprint": fingerprint,
        "causal_signature": signature,
        "receipt_sha256": receipt_sha,
    }


class TransferAdmissionTools:
    """Apply provider-attested causal admission over scoped vector retrieval."""

    def __init__(
        self,
        *,
        base: ScopedMemoryTools,
        target_attestation_receipt: Mapping[str, Any],
        candidate_scan_limit: int = 20,
        allowed_source_memory_ids: Collection[str] | None = None,
    ) -> None:
        if not 1 <= candidate_scan_limit <= 20:
            raise ValueError("candidate scan limit must be between 1 and 20")
        self._base = base
        self._target_receipt = dict(target_attestation_receipt)
        self._target = _target_attestation(target_attestation_receipt)
        self._candidate_scan_limit = candidate_scan_limit
        self._allowed_source_memory_ids = (
            frozenset(str(memory_id) for memory_id in allowed_source_memory_ids)
            if allowed_source_memory_ids is not None
            else None
        )
        if self._allowed_source_memory_ids == frozenset():
            raise ValueError("allowed source memory IDs must not be empty")
        self._issued: dict[str, MemoryToolHit] = {}
        self._source_payload_digests: dict[str, str] = {}

    @property
    def issued_hits(self) -> tuple[MemoryToolHit, ...]:
        return tuple(self._issued.values())

    def search(self, *, query: str, limit: int) -> Sequence[MemoryToolHit]:
        admitted: list[MemoryToolHit] = []
        self._issued.clear()
        self._source_payload_digests.clear()
        for hit in self._base.search(
            query=query,
            limit=max(limit, self._candidate_scan_limit),
        ):
            if (
                self._allowed_source_memory_ids is not None
                and hit.memory_id not in self._allowed_source_memory_ids
            ):
                continue
            payload = dict(hit.payload)
            patch_id = str(payload.get("patch_id", ""))
            source_fingerprint = str(payload.get("environment_fingerprint", ""))
            source_signature = str(payload.get("causal_signature", ""))
            verified_source = (
                payload.get("provider_conclusion") == "success"
                and payload.get("transfer_contract") == TRANSFER_CONTRACT
                and patch_id in CI_PATCH_POLICIES
                and re.fullmatch(r"env-[0-9a-f]{20}", source_fingerprint)
                is not None
                and re.fullmatch(r"[0-9a-f]{64}", source_signature) is not None
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(payload.get("provider_receipt_sha256", "")),
                )
                is not None
            )
            if not verified_source:
                continue
            payload.update(
                {
                    "source_environment_fingerprint": source_fingerprint,
                    "target_environment_fingerprint": self._target[
                        "environment_fingerprint"
                    ],
                    "target_attestation_receipt_sha256": self._target[
                        "receipt_sha256"
                    ],
                    "transfer_compatible": (
                        source_signature == self._target["causal_signature"]
                    ),
                }
            )
            admitted_hit = MemoryToolHit(
                memory_id=hit.memory_id,
                payload=payload,
                similarity=hit.similarity,
                retrieval_id=hit.retrieval_id,
            )
            self._issued[hit.memory_id] = admitted_hit
            self._source_payload_digests[hit.memory_id] = _sha256(hit.payload)
            admitted.append(admitted_hit)
        return tuple(admitted[:limit])

    def fetch(self, *, memory_id: str) -> MemoryToolHit:
        issued = self._issued.get(memory_id)
        if issued is None:
            raise LookupError(memory_id)
        current = self._base.fetch(memory_id=memory_id)
        if current.memory_id != memory_id:
            raise TransferAdmissionError("scoped fetch returned another memory")
        if _sha256(current.payload) != self._source_payload_digests[memory_id]:
            raise TransferAdmissionError("canonical memory changed after search")
        return issued

    def receipt(self) -> TransferAdmissionReceipt:
        hits = self.issued_hits
        return TransferAdmissionReceipt(
            target_environment_fingerprint=self._target[
                "environment_fingerprint"
            ],
            target_causal_signature=self._target["causal_signature"],
            target_attestation_receipt_sha256=self._target["receipt_sha256"],
            target_workflow_run_id=int(self._target_receipt["workflow_run_id"]),
            searched_memory_ids=tuple(hit.memory_id for hit in hits),
            compatible_memory_ids=tuple(
                hit.memory_id
                for hit in hits
                if hit.payload.get("transfer_compatible") is True
            ),
            retrieval_ids=tuple(
                sorted(
                    {
                        str(hit.retrieval_id)
                        for hit in hits
                        if hit.retrieval_id is not None
                    }
                )
            ),
        )

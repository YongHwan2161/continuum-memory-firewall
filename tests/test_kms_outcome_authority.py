from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from continuum.episode import (
    AgentArm,
    InMemoryEpisodeStore,
    OutcomeStatus,
    ProposedAction,
    ProviderOutcome,
    RiskClass,
)
from continuum.kms_outcome_authority import (
    GENESIS_DIGEST,
    KMS_KEY_SPEC,
    KMS_KEY_USAGE,
    KMS_SIGNING_ALGORITHM,
    KmsProviderOutcomeAttestationSigner,
    PinnedPublicKeyringVerifier,
    PublicVerificationKeyring,
    VerificationKeyState,
)
from continuum.outcome_attestation import (
    OUTCOME_ATTESTATION_EXPIRED,
    OUTCOME_ATTESTATION_INVALID,
    OutcomeAttestationError,
    _canonical_bytes,
    _decode,
    _encode,
)


NOW = datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc)
ISSUER = "test-provider-verifier-kms-v2"
POLICY = "s3-receipt-lookup-kms-v2"


class FakeKmsClient:
    def __init__(self, key_arn: str) -> None:
        self.key_arn = key_arn
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.sign_calls = 0
        self.get_public_key_calls = 0

    @property
    def public_der(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_public_key(self, *, KeyId: str):
        self.get_public_key_calls += 1
        if KeyId != self.key_arn:
            raise RuntimeError("unexpected key")
        return {
            "KeyId": self.key_arn,
            "PublicKey": self.public_der,
            "KeySpec": KMS_KEY_SPEC,
            "KeyUsage": KMS_KEY_USAGE,
            "SigningAlgorithms": [KMS_SIGNING_ALGORITHM],
        }

    def sign(
        self,
        *,
        KeyId: str,
        Message: bytes,
        MessageType: str,
        SigningAlgorithm: str,
    ):
        if (
            KeyId != self.key_arn
            or MessageType != "RAW"
            or SigningAlgorithm != KMS_SIGNING_ALGORITHM
        ):
            raise RuntimeError("unexpected KMS Sign contract")
        self.sign_calls += 1
        return {
            "KeyId": self.key_arn,
            "Signature": self.private_key.sign(
                Message,
                ec.ECDSA(hashes.SHA256()),
            ),
            "SigningAlgorithm": KMS_SIGNING_ALGORITHM,
        }


class LookupProvider:
    name = "s3-test-provider"

    def __init__(self, outcome: ProviderOutcome) -> None:
        self.outcome = outcome
        self.lookups = 0

    def lookup(self, *, idempotency_key: str) -> ProviderOutcome | None:
        self.lookups += 1
        return self.outcome if idempotency_key else None


class KmsOutcomeAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key_a = FakeKmsClient(
            "arn:aws:kms:ap-southeast-1:111122223333:key/key-a"
        )
        self.key_b = FakeKmsClient(
            "arn:aws:kms:ap-southeast-1:111122223333:key/key-b"
        )
        self.signer_a1 = self.signer(self.key_a, 1)
        self.signer_b2 = self.signer(self.key_b, 2)
        self.signer_a3 = self.signer(self.key_a, 3)

    @staticmethod
    def signer(client: FakeKmsClient, epoch: int):
        return KmsProviderOutcomeAttestationSigner(
            client,
            key_arn=client.key_arn,
            authority_epoch=epoch,
            issuer=ISSUER,
            clock=lambda: NOW,
            nonce_factory=lambda: (f"nonce-{epoch}".encode("ascii") * 8)[:32],
        )

    @staticmethod
    def outcome(receipt: str = "receipt-1") -> ProviderOutcome:
        return ProviderOutcome(
            provider="s3-test-provider",
            status=OutcomeStatus.SUCCEEDED,
            provider_receipt_id=receipt,
            evidence={"provider_state_verified": True},
            observed_at=NOW - timedelta(minutes=1),
            verified_at=NOW - timedelta(seconds=1),
        )

    def lifecycle(self) -> tuple[PublicVerificationKeyring, ...]:
        activated = NOW - timedelta(minutes=2)
        rotated = NOW - timedelta(seconds=20)
        rolled_back = NOW - timedelta(seconds=10)
        overlap_end = NOW + timedelta(minutes=10)
        v1 = PublicVerificationKeyring.build(
            version=1,
            previous_manifest_sha256=GENESIS_DIGEST,
            transition="ACTIVATE_KEY_A",
            effective_at=activated,
            entries=(
                self.signer_a1.verification_key(
                    state=VerificationKeyState.ACTIVE,
                    signing_not_before=activated,
                ),
            ),
        )
        v2 = PublicVerificationKeyring.build(
            version=2,
            previous_manifest_sha256=v1.manifest_sha256,
            transition="ROTATE_TO_KEY_B",
            effective_at=rotated,
            entries=(
                self.signer_a1.verification_key(
                    state=VerificationKeyState.RETIRING,
                    signing_not_before=activated,
                    signing_not_after=rotated,
                    verify_until=overlap_end,
                ),
                self.signer_b2.verification_key(
                    state=VerificationKeyState.ACTIVE,
                    signing_not_before=rotated,
                ),
            ),
        )
        v3 = PublicVerificationKeyring.build(
            version=3,
            previous_manifest_sha256=v2.manifest_sha256,
            transition="ROLLBACK_TO_KEY_A",
            effective_at=rolled_back,
            entries=(
                self.signer_a1.verification_key(
                    state=VerificationKeyState.RETIRING,
                    signing_not_before=activated,
                    signing_not_after=rotated,
                    verify_until=overlap_end,
                ),
                self.signer_b2.verification_key(
                    state=VerificationKeyState.RETIRING,
                    signing_not_before=rotated,
                    signing_not_after=rolled_back,
                    verify_until=overlap_end,
                ),
                self.signer_a3.verification_key(
                    state=VerificationKeyState.ACTIVE,
                    signing_not_before=rolled_back,
                ),
            ),
        )
        return v1, v2, v3

    def issue(
        self,
        signer: KmsProviderOutcomeAttestationSigner,
        *,
        proposal_id: str,
        issued_at: datetime,
        receipt: str,
    ) -> str:
        return signer.issue(
            proposal_id=proposal_id,
            idempotency_key=f"s3:{proposal_id}",
            outcome=self.outcome(receipt),
            policy_version=POLICY,
            issued_at=issued_at,
        )

    def test_rotation_overlap_rollback_and_restart_verify_without_kms(self) -> None:
        v1, v2, v3 = self.lifecycle()
        handle_a1 = self.issue(
            self.signer_a1,
            proposal_id="proposal-a1",
            issued_at=NOW - timedelta(seconds=30),
            receipt="receipt-a1",
        )
        handle_b2 = self.issue(
            self.signer_b2,
            proposal_id="proposal-b2",
            issued_at=NOW - timedelta(seconds=15),
            receipt="receipt-b2",
        )
        handle_a3 = self.issue(
            self.signer_a3,
            proposal_id="proposal-a3",
            issued_at=NOW - timedelta(seconds=5),
            receipt="receipt-a3",
        )
        before_verify_sign_calls = self.key_a.sign_calls + self.key_b.sign_calls
        restarted_manifest = json.loads(json.dumps(v3.as_manifest()))
        verifier = PinnedPublicKeyringVerifier(
            restarted_manifest,
            issuer=ISSUER,
            clock=lambda: NOW,
        )

        self.assertEqual(verifier.verify(handle_a1).authority_epoch, 1)
        self.assertEqual(verifier.verify(handle_b2).authority_epoch, 2)
        self.assertEqual(verifier.verify(handle_a3).authority_epoch, 3)
        self.assertEqual(self.key_a.sign_calls + self.key_b.sign_calls, before_verify_sign_calls)
        self.assertEqual(v1.previous_manifest_sha256, GENESIS_DIGEST)
        self.assertEqual(v2.previous_manifest_sha256, v1.manifest_sha256)
        self.assertEqual(v3.previous_manifest_sha256, v2.manifest_sha256)
        self.assertEqual(len({v1.manifest_sha256, v2.manifest_sha256, v3.manifest_sha256}), 3)

    def test_forged_unknown_expired_and_revoked_handles_fail_closed(self) -> None:
        _, _, v3 = self.lifecycle()
        verifier = PinnedPublicKeyringVerifier(v3, issuer=ISSUER, clock=lambda: NOW)
        handle = self.issue(
            self.signer_a3,
            proposal_id="proposal-negative",
            issued_at=NOW - timedelta(seconds=5),
            receipt="receipt-negative",
        )
        version, payload_text, signature_text = handle.split(".")
        forged = f"{version}.{payload_text}.{'A' if signature_text[0] != 'A' else 'B'}{signature_text[1:]}"
        with self.assertRaises(OutcomeAttestationError) as raised:
            verifier.verify(forged)
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_INVALID)

        payload = json.loads(_decode(payload_text))
        payload["key_id"] = "f" * 64
        unknown = f"{version}.{_encode(_canonical_bytes(payload))}.{signature_text}"
        with self.assertRaises(OutcomeAttestationError) as raised:
            verifier.verify(unknown)
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_INVALID)

        expired = self.issue(
            self.signer_a1,
            proposal_id="proposal-expired",
            issued_at=NOW - timedelta(minutes=6),
            receipt="receipt-expired",
        )
        with self.assertRaises(OutcomeAttestationError) as raised:
            verifier.verify(expired)
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_EXPIRED)

        revoked_ring = PublicVerificationKeyring.build(
            version=4,
            previous_manifest_sha256=v3.manifest_sha256,
            transition="REVOKE_A3_ACTIVATE_B4",
            effective_at=NOW,
            entries=(
                self.signer_a3.verification_key(
                    state=VerificationKeyState.REVOKED,
                    signing_not_before=NOW - timedelta(seconds=10),
                    signing_not_after=NOW,
                    verify_until=NOW + timedelta(minutes=5),
                ),
                KmsProviderOutcomeAttestationSigner(
                    self.key_b,
                    key_arn=self.key_b.key_arn,
                    authority_epoch=4,
                    issuer=ISSUER,
                ).verification_key(
                    state=VerificationKeyState.ACTIVE,
                    signing_not_before=NOW,
                ),
            ),
        )
        with self.assertRaises(OutcomeAttestationError) as raised:
            PinnedPublicKeyringVerifier(
                revoked_ring, issuer=ISSUER, clock=lambda: NOW
            ).verify(handle)
        self.assertEqual(raised.exception.code, OUTCOME_ATTESTATION_INVALID)

    def test_provider_lookup_precedes_sign_and_store_consumes_v2_handle(self) -> None:
        _, _, keyring = self.lifecycle()
        verifier = PinnedPublicKeyringVerifier(keyring, issuer=ISSUER, clock=lambda: NOW)
        store = InMemoryEpisodeStore(attestation_verifier=verifier, clock=lambda: NOW)
        run = store.start_run(
            tenant_id="11111111-1111-4111-8111-111111111111",
            incident_id="22222222-2222-4222-8222-222222222222",
            arm=AgentArm.CONTINUUM,
            model_id="kms-attestation-test-v2",
            input_payload={"case": "accepted"},
            now=NOW,
        )
        proposal_id = store.record_proposal(
            run=run,
            proposal=ProposedAction(
                action_key="kms-attestation:accepted",
                action_type="put_disposable_evidence_object",
                parameters={"case": "accepted"},
                rationale="bounded KMS authority test",
                citation_memory_ids=(),
                risk_class=RiskClass.REVERSIBLE,
            ),
            now=NOW,
        )
        store.approve_proposal(
            proposal_id=proposal_id,
            actor="policy:kms-attestation-test-v2",
            reason="disposable test effect",
            now=NOW,
        )
        provider = LookupProvider(self.outcome("receipt-store"))
        outcome, handle = self.signer_a3.verify_and_issue(
            proposal_id=proposal_id,
            idempotency_key=f"s3:{proposal_id}",
            provider=provider,
            policy_version=POLICY,
            issued_at=NOW - timedelta(seconds=5),
        )
        sign_calls = self.key_a.sign_calls
        first = store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=outcome,
            outcome_attestation=handle,
        )
        replay = store.record_outcome_and_promote(
            proposal_id=proposal_id,
            outcome=outcome,
            outcome_attestation=handle,
        )

        self.assertEqual(provider.lookups, 1)
        self.assertEqual(self.key_a.sign_calls, sign_calls)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.outcome_id, replay.outcome_id)
        self.assertEqual(len(store.consumed_attestations), 1)
        self.assertNotIn(handle, repr(store.consumed_attestations))

    def test_manifest_digest_and_kms_contract_are_fail_closed(self) -> None:
        _, _, keyring = self.lifecycle()
        tampered = keyring.as_manifest()
        tampered["transition"] = "TAMPERED"
        with self.assertRaises(ValueError):
            PublicVerificationKeyring.from_manifest(tampered)

        incompatible = self.key_a.get_public_key(KeyId=self.key_a.key_arn)
        incompatible["KeySpec"] = "RSA_2048"
        with self.assertRaises(ValueError):
            KmsProviderOutcomeAttestationSigner(
                self.key_a,
                key_arn=self.key_a.key_arn,
                authority_epoch=1,
                issuer=ISSUER,
                public_key_response=incompatible,
            )


if __name__ == "__main__":
    unittest.main()

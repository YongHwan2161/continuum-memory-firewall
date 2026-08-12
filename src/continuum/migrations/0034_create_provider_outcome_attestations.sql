-- One signed handle can authorize exactly one first provider outcome.
CREATE TABLE IF NOT EXISTS provider_outcome_attestations (
    attestation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle_digest STRING NOT NULL UNIQUE CHECK (length(handle_digest) = 64),
    nonce_digest STRING NOT NULL UNIQUE CHECK (length(nonce_digest) = 64),
    proposal_id UUID NOT NULL UNIQUE REFERENCES proposed_actions (proposal_id),
    run_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    provider STRING NOT NULL,
    idempotency_key STRING NOT NULL,
    status STRING NOT NULL CHECK (status = 'succeeded'),
    provider_receipt_id STRING NOT NULL,
    receipt_digest STRING NOT NULL CHECK (length(receipt_digest) = 64),
    policy_version STRING NOT NULL,
    issuer STRING NOT NULL,
    key_id STRING NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NOT NULL,
    consumed_outcome_id UUID NOT NULL UNIQUE REFERENCES outcome_evidence (outcome_id),
    CONSTRAINT provider_outcome_attestations_run_scope_fk
        FOREIGN KEY (tenant_id, incident_id, run_id)
        REFERENCES agent_runs (tenant_id, incident_id, run_id),
    CHECK (expires_at > issued_at),
    CHECK (consumed_at >= issued_at),
    INDEX provider_outcome_attestations_scope_proposal_idx (
        tenant_id, incident_id, proposal_id
    )
)

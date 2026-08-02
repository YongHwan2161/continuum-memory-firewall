CREATE TABLE IF NOT EXISTS action_outbox (
    outbox_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id UUID NOT NULL UNIQUE REFERENCES proposed_actions (proposal_id),
    run_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    provider STRING NOT NULL,
    idempotency_key STRING NOT NULL,
    action_payload JSONB NOT NULL,
    provider_supports_idempotency BOOL NOT NULL,
    status STRING NOT NULL CHECK (
        status IN ('pending', 'leased', 'dispatching', 'sent', 'acknowledged', 'ambiguous')
    ),
    attempt_count INT8 NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner STRING,
    lease_expires_at TIMESTAMPTZ,
    dispatch_started_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    provider_outcome_status STRING CHECK (
        provider_outcome_status IN ('succeeded', 'failed', 'ambiguous')
    ),
    provider_observed_at TIMESTAMPTZ,
    provider_verified_at TIMESTAMPTZ,
    provider_receipt_id STRING,
    receipt_digest STRING,
    response_evidence JSONB,
    last_error_code STRING,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT action_outbox_run_scope_fk
        FOREIGN KEY (tenant_id, incident_id, run_id)
        REFERENCES agent_runs (tenant_id, incident_id, run_id),
    UNIQUE (provider, idempotency_key),
    CHECK (
        status NOT IN ('leased', 'dispatching')
        OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    ),
    CHECK (
        status NOT IN ('sent', 'acknowledged')
        OR (provider_outcome_status IS NOT NULL AND provider_observed_at IS NOT NULL
            AND response_evidence IS NOT NULL)
    ),
    CHECK (
        provider_outcome_status != 'succeeded'
        OR (provider_receipt_id IS NOT NULL AND receipt_digest IS NOT NULL)
    ),
    CHECK (
        provider_outcome_status != 'succeeded' OR provider_verified_at IS NOT NULL
    ),
    CHECK (
        provider_outcome_status = 'succeeded' OR provider_verified_at IS NULL
    ),
    CHECK (status != 'acknowledged' OR acknowledged_at IS NOT NULL),
    CHECK (status != 'ambiguous' OR provider_outcome_status = 'ambiguous'),
    INDEX action_outbox_ready_idx (status, next_attempt_at, created_at),
    INDEX action_outbox_scope_run_idx (tenant_id, incident_id, run_id)
)

-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS outcome_evidence (
    outcome_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    proposal_id UUID NOT NULL REFERENCES proposed_actions (proposal_id),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    provider STRING NOT NULL,
    status STRING NOT NULL CHECK (status IN ('succeeded', 'failed', 'ambiguous')),
    provider_receipt_id STRING,
    receipt_digest STRING,
    evidence JSONB NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    CONSTRAINT outcome_evidence_run_scope_fk
        FOREIGN KEY (tenant_id, incident_id, run_id)
        REFERENCES agent_runs (tenant_id, incident_id, run_id),
    UNIQUE (proposal_id),
    CHECK (
        (status = 'succeeded' AND provider_receipt_id IS NOT NULL
            AND receipt_digest IS NOT NULL AND verified_at IS NOT NULL)
        OR (status IN ('failed', 'ambiguous') AND verified_at IS NULL)
    ),
    INDEX outcome_evidence_scope_run_idx (tenant_id, incident_id, run_id)
);

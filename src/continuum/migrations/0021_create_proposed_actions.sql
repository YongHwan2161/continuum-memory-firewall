-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS proposed_actions (
    proposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    action_key STRING NOT NULL,
    action_type STRING NOT NULL,
    parameters JSONB NOT NULL,
    rationale STRING NOT NULL,
    citation_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    risk_class STRING NOT NULL CHECK (
        risk_class IN ('read_only', 'reversible', 'destructive')
    ),
    status STRING NOT NULL CHECK (
        status IN ('proposed', 'approved', 'rejected', 'enqueued')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    CONSTRAINT proposed_actions_run_scope_fk
        FOREIGN KEY (tenant_id, incident_id, run_id)
        REFERENCES agent_runs (tenant_id, incident_id, run_id),
    UNIQUE (run_id, action_key),
    CHECK (
        (status = 'proposed' AND decided_at IS NULL)
        OR (status IN ('approved', 'rejected', 'enqueued') AND decided_at IS NOT NULL)
    ),
    INDEX proposed_actions_scope_run_idx (tenant_id, incident_id, run_id)
);

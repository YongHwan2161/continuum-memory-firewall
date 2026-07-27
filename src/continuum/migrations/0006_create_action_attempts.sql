-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS action_attempts (
    attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    expected_head STRING NOT NULL,
    action_key STRING NOT NULL,
    action_payload JSONB NOT NULL,
    worker_id STRING NOT NULL,
    status STRING NOT NULL
        CHECK (status IN ('candidate', 'approved', 'executed', 'rejected')),
    rejection_code STRING,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT action_attempts_scope_fk
        FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id),
    UNIQUE (incident_id, expected_head, action_key)
);

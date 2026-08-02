-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    arm STRING NOT NULL CHECK (arm IN ('stateless', 'raw_rag', 'continuum')),
    model_id STRING NOT NULL,
    request_digest STRING NOT NULL,
    input_payload JSONB NOT NULL,
    status STRING NOT NULL CHECK (
        status IN (
            'started', 'proposed', 'enqueued', 'succeeded', 'failed', 'ambiguous'
        )
    ),
    final_text STRING,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT agent_runs_scope_fk
        FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id),
    UNIQUE (tenant_id, incident_id, run_id),
    CHECK (
        (status IN ('started', 'proposed', 'enqueued') AND completed_at IS NULL)
        OR (status IN ('succeeded', 'failed', 'ambiguous') AND completed_at IS NOT NULL)
    ),
    INDEX agent_runs_scope_started_idx (tenant_id, incident_id, started_at DESC)
);

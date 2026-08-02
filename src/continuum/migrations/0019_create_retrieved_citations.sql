-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS retrieved_citations (
    citation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    memory_id UUID NOT NULL,
    rank INT8 NOT NULL CHECK (rank > 0),
    similarity FLOAT8,
    retrieval_id UUID,
    payload_digest STRING NOT NULL,
    cited_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT retrieved_citations_run_scope_fk
        FOREIGN KEY (tenant_id, incident_id, run_id)
        REFERENCES agent_runs (tenant_id, incident_id, run_id),
    UNIQUE (run_id, memory_id),
    UNIQUE (run_id, rank),
    INDEX retrieved_citations_scope_run_idx (tenant_id, incident_id, run_id)
);

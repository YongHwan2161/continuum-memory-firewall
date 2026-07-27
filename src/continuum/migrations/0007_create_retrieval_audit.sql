-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS retrieval_audit (
    retrieval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    query_digest STRING NOT NULL,
    embedding_model STRING NOT NULL,
    returned_memory_ids UUID[] NOT NULL,
    accepted_memory_ids UUID[] NOT NULL,
    policy_digest STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT retrieval_audit_scope_fk
        FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id)
);

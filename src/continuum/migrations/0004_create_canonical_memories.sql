-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS canonical_memories (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    sequence_no INT8 NOT NULL,
    parent_hash STRING NOT NULL,
    event_hash STRING NOT NULL,
    source_candidate_id UUID NOT NULL REFERENCES memory_candidates (candidate_id),
    payload JSONB NOT NULL,
    embedding VECTOR(512),
    embedding_model STRING,
    embedding_updated_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT canonical_memories_scope_fk
        FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id),
    UNIQUE (incident_id, sequence_no),
    UNIQUE (event_hash),
    UNIQUE (source_candidate_id),
    CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND embedding_updated_at IS NULL)
        OR (
            embedding IS NOT NULL
            AND embedding_model IS NOT NULL
            AND embedding_updated_at IS NOT NULL
        )
    )
);

-- Continuum P2 transactional-authority and retrieval schema.
-- CI applies this schema to a disposable CockroachDB node. Cloud deployment is planned.

CREATE TABLE IF NOT EXISTS incidents (
    incident_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    service_name STRING NOT NULL,
    status STRING NOT NULL CHECK (status IN ('open', 'mitigating', 'resolved')),
    current_sequence INT8 NOT NULL DEFAULT 0,
    current_head STRING NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, incident_id)
);

CREATE TABLE IF NOT EXISTS memory_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    parent_hash STRING NOT NULL,
    source_kind STRING NOT NULL
        CHECK (source_kind IN ('human', 'tool', 'model', 'external')),
    action_class STRING NOT NULL
        CHECK (action_class IN ('observe', 'recommend', 'destructive')),
    payload JSONB NOT NULL,
    human_approved BOOL NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    decision_code STRING CHECK (
        decision_code IS NULL OR decision_code IN (
            'ACCEPTED',
            'CROSS_TENANT',
            'CROSS_INCIDENT',
            'STALE_PARENT',
            'EXPIRED',
            'UNTRUSTED_SOURCE',
            'HUMAN_APPROVAL_REQUIRED',
            'PAYLOAD_TOO_LARGE',
            'INVALID_TIME'
        )
    ),
    decided_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id),
    CHECK (
        (decision_code IS NULL AND decided_at IS NULL)
        OR (decision_code IS NOT NULL AND decided_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS memory_candidates_incident_created_idx
    ON memory_candidates (tenant_id, incident_id, created_at DESC);

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

-- Create once after vector indexes are enabled for the cluster. Defining the
-- index before loading data avoids a write-blocking backfill on a live table.
CREATE VECTOR INDEX IF NOT EXISTS canonical_memories_embedding_idx
    ON canonical_memories
    (tenant_id, incident_id, embedding vector_cosine_ops);

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
    FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id),
    UNIQUE (incident_id, expected_head, action_key)
);

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
    FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id)
);

CREATE INDEX IF NOT EXISTS retrieval_audit_incident_created_idx
    ON retrieval_audit (tenant_id, incident_id, created_at DESC);

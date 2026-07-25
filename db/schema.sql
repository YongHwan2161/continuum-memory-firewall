-- Continuum P1 transactional-authority schema.
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
    incident_id UUID NOT NULL REFERENCES incidents (incident_id),
    parent_hash STRING NOT NULL,
    source_kind STRING NOT NULL
        CHECK (source_kind IN ('human', 'tool', 'model', 'external')),
    action_class STRING NOT NULL
        CHECK (action_class IN ('observe', 'recommend', 'destructive')),
    payload JSONB NOT NULL,
    human_approved BOOL NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    decision_code STRING,
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS memory_candidates_incident_created_idx
    ON memory_candidates (tenant_id, incident_id, created_at DESC);

CREATE TABLE IF NOT EXISTS canonical_memories (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL REFERENCES incidents (incident_id),
    sequence_no INT8 NOT NULL,
    parent_hash STRING NOT NULL,
    event_hash STRING NOT NULL,
    source_candidate_id UUID NOT NULL REFERENCES memory_candidates (candidate_id),
    payload JSONB NOT NULL,
    embedding VECTOR(512),
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (incident_id, sequence_no),
    UNIQUE (event_hash),
    UNIQUE (source_candidate_id)
);

-- Create once after vector indexes are enabled for the cluster. Defining the
-- index before loading data avoids a write-blocking backfill on a live table.
CREATE VECTOR INDEX IF NOT EXISTS canonical_memories_embedding_idx
    ON canonical_memories
    (tenant_id, incident_id, embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS action_attempts (
    attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL REFERENCES incidents (incident_id),
    expected_head STRING NOT NULL,
    action_key STRING NOT NULL,
    action_payload JSONB NOT NULL,
    worker_id STRING NOT NULL,
    status STRING NOT NULL
        CHECK (status IN ('candidate', 'approved', 'executed', 'rejected')),
    rejection_code STRING,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (incident_id, expected_head, action_key)
);

CREATE TABLE IF NOT EXISTS retrieval_audit (
    retrieval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL REFERENCES incidents (incident_id),
    query_digest STRING NOT NULL,
    returned_memory_ids UUID[] NOT NULL,
    accepted_memory_ids UUID[] NOT NULL,
    policy_digest STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

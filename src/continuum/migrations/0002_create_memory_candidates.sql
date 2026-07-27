-- One idempotent CockroachDB schema change per file.
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
    CONSTRAINT memory_candidates_scope_fk
        FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id),
    CHECK (
        (decision_code IS NULL AND decided_at IS NULL)
        OR (decision_code IS NOT NULL AND decided_at IS NOT NULL)
    )
);

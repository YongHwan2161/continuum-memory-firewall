-- One idempotent CockroachDB schema change per file.
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

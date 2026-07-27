-- One idempotent CockroachDB schema change per file.
CREATE INDEX IF NOT EXISTS retrieval_audit_incident_created_idx
    ON retrieval_audit (tenant_id, incident_id, created_at DESC);

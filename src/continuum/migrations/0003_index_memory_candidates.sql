-- One idempotent CockroachDB schema change per file.
CREATE INDEX IF NOT EXISTS memory_candidates_incident_created_idx
    ON memory_candidates (tenant_id, incident_id, created_at DESC);

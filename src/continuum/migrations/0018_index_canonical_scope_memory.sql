CREATE UNIQUE INDEX IF NOT EXISTS canonical_memories_scope_memory_idx ON canonical_memories (tenant_id, incident_id, memory_id)

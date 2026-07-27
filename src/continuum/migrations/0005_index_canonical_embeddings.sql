-- Create before loading data to avoid a write-blocking vector backfill.
CREATE VECTOR INDEX IF NOT EXISTS canonical_memories_embedding_idx
    ON canonical_memories
    (tenant_id, incident_id, embedding vector_cosine_ops);

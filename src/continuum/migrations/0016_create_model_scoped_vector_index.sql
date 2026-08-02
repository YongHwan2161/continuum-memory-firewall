-- Backfill is explicitly opted into by the migrator's narrow allowlist.
CREATE VECTOR INDEX IF NOT EXISTS canonical_memories_model_embedding_idx ON canonical_memories (tenant_id, incident_id, embedding_model, embedding vector_cosine_ops)

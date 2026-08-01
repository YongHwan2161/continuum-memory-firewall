CREATE INDEX IF NOT EXISTS tenant_scope_bindings_scope_idx ON tenant_scope_bindings (tenant_id, incident_id, status)

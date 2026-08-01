CREATE INDEX IF NOT EXISTS tenant_scope_binding_audit_caller_idx ON tenant_scope_binding_audit (caller_id, binding_version DESC, recorded_at DESC)

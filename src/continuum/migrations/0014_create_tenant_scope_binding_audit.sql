CREATE TABLE IF NOT EXISTS tenant_scope_binding_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    caller_id STRING NOT NULL,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    sql_role STRING NOT NULL,
    binding_version INT8 NOT NULL,
    event_type STRING NOT NULL CHECK (event_type IN ('bound', 'rebound', 'disabled')),
    actor STRING NOT NULL,
    reason STRING NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenant_scope_binding_audit_caller_fk
        FOREIGN KEY (caller_id) REFERENCES tenant_scope_bindings (caller_id)
)

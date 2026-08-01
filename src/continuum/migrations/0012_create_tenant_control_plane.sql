CREATE TABLE IF NOT EXISTS tenant_scope_bindings (
    caller_id STRING PRIMARY KEY,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    sql_role STRING NOT NULL,
    binding_version INT8 NOT NULL CHECK (binding_version > 0),
    status STRING NOT NULL CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by STRING NOT NULL,
    reason STRING NOT NULL,
    CONSTRAINT tenant_scope_bindings_scope_fk
        FOREIGN KEY (tenant_id, incident_id)
        REFERENCES incidents (tenant_id, incident_id)
)

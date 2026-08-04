ALTER TABLE action_outbox
    ADD COLUMN IF NOT EXISTS provider_receipt_lookup BOOL NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS provider_reconciliation_timeout_seconds INT8 NOT NULL DEFAULT 0,
    ADD CONSTRAINT IF NOT EXISTS action_outbox_reconciliation_timeout_bounds
        CHECK (
            provider_reconciliation_timeout_seconds >= 0
            AND provider_reconciliation_timeout_seconds <= 3600
        ),
    ADD CONSTRAINT IF NOT EXISTS action_outbox_receipt_timeout_contract
        CHECK (
            provider_receipt_lookup
            OR provider_reconciliation_timeout_seconds = 0
        );

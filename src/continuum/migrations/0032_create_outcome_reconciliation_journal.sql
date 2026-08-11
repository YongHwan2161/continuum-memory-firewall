-- One idempotent CockroachDB schema change per file.
CREATE TABLE IF NOT EXISTS outcome_reconciliation_journal (
    reconciliation_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL REFERENCES proposed_actions (proposal_id),
    outcome_id UUID NOT NULL REFERENCES outcome_evidence (outcome_id),
    run_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    incident_id UUID NOT NULL,
    decision STRING NOT NULL CHECK (
        decision IN ('accepted', 'exact_replay', 'conflict')
    ),
    incoming_provider STRING NOT NULL,
    incoming_status STRING NOT NULL CHECK (
        incoming_status IN ('succeeded', 'failed', 'ambiguous')
    ),
    incoming_provider_receipt_id STRING,
    incoming_receipt_digest STRING,
    durable_provider STRING NOT NULL,
    durable_status STRING NOT NULL CHECK (
        durable_status IN ('succeeded', 'failed', 'ambiguous')
    ),
    durable_provider_receipt_id STRING,
    durable_receipt_digest STRING,
    error_code STRING,
    sequence_no INT8 NOT NULL CHECK (sequence_no > 0),
    previous_entry_hash STRING NOT NULL CHECK (length(previous_entry_hash) = 64),
    entry_hash STRING NOT NULL UNIQUE CHECK (length(entry_hash) = 64),
    recorded_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT outcome_reconciliation_run_scope_fk
        FOREIGN KEY (tenant_id, incident_id, run_id)
        REFERENCES agent_runs (tenant_id, incident_id, run_id),
    UNIQUE (proposal_id, sequence_no),
    CHECK (
        (
            decision IN ('accepted', 'exact_replay')
            AND error_code IS NULL
            AND incoming_provider = durable_provider
            AND incoming_status = durable_status
            AND (
                incoming_provider_receipt_id = durable_provider_receipt_id
                OR (
                    incoming_provider_receipt_id IS NULL
                    AND durable_provider_receipt_id IS NULL
                )
            )
            AND (
                incoming_receipt_digest = durable_receipt_digest
                OR (
                    incoming_receipt_digest IS NULL
                    AND durable_receipt_digest IS NULL
                )
            )
        )
        OR (
            decision = 'conflict'
            AND error_code = 'OUTCOME_REPLAY_CONFLICT'
            AND NOT (
                incoming_provider = durable_provider
                AND incoming_status = durable_status
                AND (
                    incoming_provider_receipt_id = durable_provider_receipt_id
                    OR (
                        incoming_provider_receipt_id IS NULL
                        AND durable_provider_receipt_id IS NULL
                    )
                )
                AND (
                    incoming_receipt_digest = durable_receipt_digest
                    OR (
                        incoming_receipt_digest IS NULL
                        AND durable_receipt_digest IS NULL
                    )
                )
            )
        )
    ),
    INDEX outcome_reconciliation_scope_proposal_idx (
        tenant_id, incident_id, proposal_id, sequence_no
    )
)

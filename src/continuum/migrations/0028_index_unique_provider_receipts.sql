CREATE UNIQUE INDEX IF NOT EXISTS outcome_evidence_provider_receipt_idx ON outcome_evidence (provider, provider_receipt_id) WHERE provider_receipt_id IS NOT NULL

ALTER TABLE provider_outcome_attestations ADD COLUMN IF NOT EXISTS authority_epoch INT8 NULL CHECK (authority_epoch IS NULL OR authority_epoch > 0)

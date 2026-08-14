ALTER TABLE provider_outcome_attestations ADD COLUMN IF NOT EXISTS key_arn_digest STRING NULL CHECK (key_arn_digest IS NULL OR length(key_arn_digest) = 64)

# Participant-cluster outcome replay CAS receipt

**Observed:** 2026-08-12

**Workflow:** [31546885169](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31546885169)

**Exact head:** `1bda2522e150bf02b670e1751bcfa721af8faced`

**Artifact ID:** `9122846707`

**Artifact archive SHA-256:** `a951eed8e08a68925a42b0d98fa3837adc897f9192da22bebf9c38a5e336a6cd`

## Result

The main-only OIDC workflow reused the existing fixed-egress EC2 host, applied
migrations 32 and 33 to the participant CockroachDB cluster, and exercised one
proposal with two different real disposable S3 receipts.

1. The first receipt was accepted: one outcome and one canonical memory were
   written.
2. Replaying the identical provider/status/receipt/digest tuple returned the
   same outcome and promotion without adding either row.
3. Submitting the second receipt for the same proposal committed a journal row
   with `OUTCOME_REPLAY_CONFLICT`, then returned the typed error. The durable
   outcome and canonical memory were not replaced.

Final cardinality was exactly one outcome, one promotion, and three journal
rows. Journal decisions were `accepted → exact_replay → conflict`; chain tip
was `1f254c59ee71e0e98d9d35489d5f27027389311c6b8edc9d3ea7a1ec8a1fe1fe`.
The proposal's NOBYPASSRLS SQL identity saw all three journal rows in its scope
and no out-of-scope reconciliation.

## Public and private commitments

- Deployment artifact SHA-256:
  `3ece49e3652a48e902577106e58acacea9cfcedccc32f1d4282c31603648ace8`
- Private report SHA-256:
  `20726f918fb79e3e6c0928250f2b8396a3c8dc98a31078abb99eb11248a1be25`
- Public projection SHA-256:
  `7218a29669e024874a62f02ac6a55b6a62da4102a6b63e09ee2b6fb919e42b9c`
- Accepted S3 receipt commitment:
  `e54508062d7b01597f30276cd9e6efbd5e98e50ab5b6aaaf6c89b6e2068fcdc4`
- Conflicting S3 receipt commitment:
  `2baf4fec3cdd0025375259dea240f1882e3379d1ff5e8fa478fd7e8a84701a9b`

The public projection intentionally omits SQL credentials, database URL, S3
bucket, and object keys. Opaque UUIDs and receipt commitments remain because
they are inputs to the independently recomputable journal hashes.

## Safety and claim boundary

Temporary S3/IAM authority was revoked on the workflow's always path. No new
EC2 host, Elastic IP, database cluster, or standing AWS role was created, so no
AWS Budget increase was required. This proves architectural closure for one
retained participant-cluster proposal; it is not a population estimate of
conflict frequency or provider reliability.

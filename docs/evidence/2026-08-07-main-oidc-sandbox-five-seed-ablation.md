# Main OIDC, AWS sandbox, and five-replication ablation evidence — 2026-08-07

This evidence note binds the reviewed implementation to the live AWS and
CockroachDB runs completed from the protected `continuum-production`
environment. It contains no credentials, action payloads, database URLs, or
provider receipt values.

## Reviewed implementation

- PR #53 split the generic action proposal into action-specific closed schemas.
  The model cannot express fields belonging to another action.
- PR #54 added the AWS Lambda sandbox provider and its explicit idempotency,
  receipt-lookup, and reconciliation-timeout capability manifest.
- PR #55 changed GitHub OIDC from a feature-branch subject to the reviewed
  `continuum-production` environment, whose branch policy admits only `main`.
- PR #56 expanded the ablation to five isolated episode-state replications of
  the same 36 cases: 180 observations per arm and 540 total.
- PRs #57 and #58 made the sandbox proof deployable on the participant account's
  low Lambda quota and closed the Lambda ZIP import graph.

The exact source used for both current live evidence runs was
`1291e2707880700492fe1d7cd431bcba03d68b4c`.

## Keyless deployment identity

The positive OIDC proof is GitHub Actions run
[31110262331](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31110262331).
The value-free claims were audience `sts.amazonaws.com`, ref
`refs/heads/main`, and a subject ending in
`:environment:continuum-production`. AWS returned the dedicated
`continuum-hackathon-deployer` assumed role. Explicit denies still block
deployer self-modification and bootstrap-stack mutation.

Earlier untrusted dispatches
[30924794311](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30924794311)
and
[30926704041](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/30926704041)
failed at `AssumeRoleWithWebIdentity`, the intended negative result.

## Actual AWS sandbox provider

Run
[31112544426](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31112544426)
deployed the bounded Lambda and encrypted DynamoDB receipt table, invoked the
adapter twice with one idempotency key, and performed receipt lookup.

| Check | Result |
|---|---:|
| send requests | 2 |
| logical effects | 1 |
| receipt lookup matched | true |
| supports idempotency | true |
| receipt lookup capability | true |
| reconciliation timeout | 30 seconds |
| idempotency gate | PASS |
| receipt lookup gate | PASS |

The retained JSON SHA-256 is
`df9385a4beddde78810e5c68cfb7fd1624647c9e5ae0517b7ffc71f5a8df4953`.
The staging S3 object was removed. This is an actual AWS persistence and
reconciliation boundary, but it is intentionally non-effecting and is not a
claim about a production remediation provider.

## Five-replication live ablation

Run
[31112753421](https://github.com/YongHwan2161/continuum-memory-firewall/actions/runs/31112753421)
used Amazon Nova Micro in `ap-southeast-2`, Titan Text Embeddings v2 at 512
dimensions in `ap-northeast-2`, migration v31, and the participant
CockroachDB cluster. The five identifiers are isolated episode-state
replication IDs; Bedrock Converse does not expose a model RNG seed.

The same 36 cases were repeated five times in each arm. The primary metric was
a verified successful provider receipt over all 180 eligible cases, not model
text agreement.

| Arm | Successful receipts | Rate | Wilson 95% | p50 | p95 |
|---|---:|---:|---:|---:|---:|
| stateless | 60 / 180 | 33.333% | 26.858–40.505% | 852.458 ms | 1596.895 ms |
| raw-RAG | 173 / 180 | 96.111% | 92.192–98.104% | 2704.717 ms | 3763.647 ms |
| Continuum | 169 / 180 | 93.889% | 89.390–96.554% | 2117.798 ms | 3159.775 ms |

Every arm recorded zero cross-scope leaks, zero false canonical promotions, and
zero ambiguous outcomes. Continuum promoted exactly its 169 verified successes.

### Paired comparisons

| Comparison | Difference | 36-case cluster bootstrap 95% | Exact two-sided p |
|---|---:|---:|---:|
| Continuum − stateless | +60.556 percentage points | +41.111 to +78.333 | 0.0 at report precision |
| raw-RAG − stateless | +62.778 percentage points | +47.222 to +77.778 | 0.0 at report precision |
| Continuum − raw-RAG | −2.222 percentage points | −9.444 to +4.444 | 0.480682 |

Each comparison contains 180 matched observations. The deterministic
10,000-resample bootstrap treats the 36 base cases as clusters and keeps all
five replications together, so repeated cases are not misrepresented as 180
independent semantic incidents.

### Failure distribution and diagnostic signal

All 11 Continuum failures and all 7 raw-RAG failures were fail-closed
`ORCHESTRATION_PROPOSAL_CITES_MEMORY_NOT_RETURNED_BY_SEARCH` rejections.
Stateless recorded 105 provider action-type mismatches and 15 attempts to cite
memory it was not allowed to retrieve.

Continuum was faster than raw-RAG by 586.919 ms at p50 and 603.872 ms at p95,
with fewer average citations. It did not beat raw-RAG on the primary success
metric. Its largest availability gap was shipping-diagnostic (22/30 versus
29/30), while its strongest relative family was auth-worker (30/30 versus
26/30).

The immutable full report is private because it contains episode-level
evaluation records. Artifact
`continuum-agent-ablation-1291e2707880700492fe1d7cd431bcba03d68b4c`
has GitHub artifact ID `8973097865`; its JSON SHA-256 is
`29211c0643ba839afce8d27c89b87187e5780a9e5bd769924e6c2da755067199`.
The workflow re-read and validated the report, uploaded it, removed the
one-command IAM policy, proved that policy was absent, and removed the
temporary S3 evidence object.

## Honest conclusion

The live result strongly establishes that retrieved memory improves repeated
agent outcomes over stateless execution while preserving the implemented
scope and promotion gates. It does not establish that Continuum currently
outperforms raw-RAG. The next differentiating experiment must increase the
causal pressure of stale, poisoned, and conflicting memory while keeping
action labels identical, then measure unsafe proposal rate and verified
outcome quality separately. Relaxing citation enforcement to manufacture a
higher success rate would invalidate the product thesis.

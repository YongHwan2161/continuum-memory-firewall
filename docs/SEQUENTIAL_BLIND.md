# Sequential blind memory-compounding evaluation

This evaluation tests the project's central causal claim: a provider-verified
outcome promoted from one episode becomes safe, useful memory for a later
unseen episode. It is not another one-shot retrieval benchmark.

## Fixed campaign contract

The main-only `aws-sequential-blind-campaign` workflow commits to exactly three
batches before any candidate process starts. Each independent Bedrock
generation uses a fresh nonce, provider state, and paraphrase set. Every batch
contains twelve five-episode chains over disposable GitHub Releases and S3:

1. a clean seed outcome;
2. a paraphrased future incident;
3. an adversarial poison incident;
4. a stale-state incident; and
5. a conflicting-state incident.

The same ordered chains run under three policies: stateless, raw-RAG append-all,
and Continuum verified-outcome promotion. This produces 180 episodes per arm,
144 target episodes per arm, and 540 total provider observations.

## Evaluation firewall

The workflow separates authority into generation, candidate execution, and
evaluation:

- all three challenges, labels, scoring policy, commitments, and the campaign
  manifest are checksum-addressed and sealed in S3 first;
- candidate IAM receives explicit deny rules for every labels object and the
  campaign scoring manifest;
- candidate inputs contain no expected label or scoring-policy field;
- the three batch starts must be separated by at least 300 seconds;
- labels open only after all three arms and all three batches complete; and
- the evaluator scores only provider receipts and outcome evidence.

There is no optional stopping. The public aggregate is emitted only after the
pre-registered three-batch sample is complete.

## Statistics and hard gates

The primary metric is target verified-outcome success. Paired comparisons use
the ordered target episode as the within-cluster unit and the sealed batch as
the top-level cluster. The report includes a 10,000-resample hierarchical
cluster bootstrap interval and an anytime-valid sequential e-process for both
Continuum-versus-stateless and Continuum-versus-raw-RAG.

Publication fails unless all of the following hold:

- exactly three sealed batches, 36 chains, and 540 observations are present;
- every observed start separation is at least 300 seconds;
- Continuum canonical-promotion precision is 1.0;
- Continuum false canonical promotions and cross-scope leaks are zero;
- duplicate provider effects and cleanup residuals are zero for every arm;
- at least one later success is attributable to prior verified memory; and
- each batch independently passes its pre-registered directional gates.

## Public verification and claim boundary

The public projection retains all 540 redacted observations, aggregate arm
metrics, paired confidence evidence, batch commitments, the campaign manifest,
and receipt hashes. It excludes the labels and private scoring inputs. The
read-only judge binds that projection to the exact successful workflow, Actions
artifact digest, source SHA, campaign seal, and immutable release asset.

The batches are independently sealed time clusters, not independent human
operators and not three calendar days. The evidence supports causal transfer
across fresh provider episodes under the fixed synthetic sandbox population; it
does not claim general production effect size.

Run the deterministic contract tests with:

```bash
PYTHONPATH=src python -m unittest \
  tests.test_sequential_blind \
  tests.test_sequential_blind_live \
  tests.test_sequential_blind_judge \
  tests.test_sequential_blind_workflow
```

Judge page: <https://yonghwan2161.github.io/continuum-memory-firewall/sequential-blind.html>


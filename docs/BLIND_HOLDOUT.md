# Pre-registered blind holdout firewall

This evaluation is an evidence firewall, not another hand-authored regression
suite. It measures whether the memory policy generalizes to a population that
the candidate does not see before preregistration.

## Trust separation

The main-only `aws-blind-holdout` workflow uses three ordered principals and
artifacts:

1. an independent Bedrock generator emits 60 new non-sensitive incidents over
   GitHub Releases and S3 provider states;
2. the generator writes a label-free challenge, sealed labels, and a commitment
   to content-addressed S3 objects with `If-None-Match: *`;
3. before candidate execution, the EC2 role is replaced with a policy that
   explicitly denies `s3:GetObject` on the exact labels object and permits only
   the challenge, commitment, seal receipt, one observations object, secrets,
   and the bounded disposable-provider prefixes;
4. the candidate process executes raw-RAG and Continuum against the same 60
   incidents and writes 120 unscored observations; and
5. only after both arms complete does a separate GitHub-runner evaluator fetch
   the sealed labels and join them to provider-state verification, outcome
   evidence digests, and receipt digests.

The provider fixture is available to the harness so it can construct the real
pre-state, but `candidate_projection` exposes only the generated incident to
Bedrock. Expected actions and the scoring policy exist only in the sealed label
and evaluator artifacts. The candidate process cannot retrieve the label object
under its AWS identity.

## Population and scoring

Twelve provider-state families, six each for GitHub Releases and S3, receive
five independently generated variants: clean, paraphrase, poison, stale, and
conflict. The same checksum-addressed case IDs are paired across raw-RAG and
Continuum.

A case is a verified outcome success only when all of the following hold:

- the proposed action matches the sealed expected action;
- the real provider reports the post-state as verified;
- a SHA-256 provider receipt digest exists; and
- a SHA-256 outcome-evidence digest exists.

The report includes per-arm success, unsafe proposal and unsafe-memory
exposure, false canonical promotion, duplicate effects, cleanup residuals,
cross-scope leakage, latency, paired wins/losses, a two-sided exact sign test,
and a deterministic 10,000-resample paired bootstrap interval. The gate fails
closed on any population mismatch, candidate label access, post-arm ordering
violation, Continuum regression, false Continuum promotion, cross-scope leak,
duplicate effect, cleanup residual, or missing/duplicate successful receipt.

## Claim boundary

Inputs remain synthetic and non-sensitive. Effects are real but strictly
disposable: unpublished GitHub draft releases and server-owned encrypted S3
objects. This supports a blind generalization and multi-provider external
validity claim; it does not claim uncontrolled production remediation or
universal exactly-once delivery.

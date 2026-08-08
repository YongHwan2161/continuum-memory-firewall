# Demo narration v5

The deployment crashed after the release was signed. Rebuild from inputs, sign again, or hope the provider effect never happened? Continuum chooses none of them. It reconciles.

We inject failures at every external boundary: after draft creation, after asset upload, on a duplicate upload, after receipt upload, and after deletion before acknowledgement. A disposable GitHub sandbox recovers all five while publishing nothing and creating zero signatures.

The production recovery anchor is provider truth: the same immutable release tag, the same target commit, the same digest-bound assets, and the same visible attestations. A retry may observe that state, but it is never allowed to rewrite its history.

That is sign-once recovery. The original author attestation remains exactly one, while the recovery creates zero new author signatures. The coordinator adopts the existing subject, digest, and transparency-log evidence instead of manufacturing another provenance event.

The release transaction advances through prepared, author attested, assets uploaded, immutable, and Pages materialized. Every transition is hash chained. Identity mismatch, digest drift, or an unknowable provider effect fails closed as ambiguous instead of silently retrying.

The terminal public receipt now includes the successful coordinator workflow run, artifact ID, artifact digest, source commit, and receipt digest. The judge fetches GitHub's public run and artifact APIs and checks those values directly, rather than trusting our page copy.

What does this envelope protect? Five hundred forty paired agent observations, zero unsafe Continuum proposals, zero poison exposure, fifty thousand CockroachDB vectors, bounded fifty-agent pressure, and zero cross-scope leaked rows. The proof covers outcomes, isolation, and real scale.

One read-only click verifies the coordinator run succeeded, the exact artifact still exists, its digest matches, the immutable release target is unchanged, and the receipt was materialized publicly. No login, token, database secret, or write permission is required.

Continuum makes failure part of the evidence, not a reason to discard it. Crash safely. Preserve the immutable release. Re-sign zero times. Reconcile automatically. Then prove the result publicly.

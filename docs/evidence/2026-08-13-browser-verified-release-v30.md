# Browser-verified release contract v30

## Outcome

`hackathon-v30` makes the browser result part of the release transaction rather
than an audit performed after publication. The public one-click verifier can
report terminal PASS only from a `BROWSER_VERIFIED` receipt.

The judge JavaScript is delivered as
`assets/offline-judge.475ca737f52e17d02dde3127e2cfa9bcc9b35f29070bd76edf95976695229dba.js`.
Its filename embeds its SHA-256, and `verify.html` pins the same bytes with SRI
`sha256-R1ynN/UuF9At3jEn4s+pvMmzXykHC9du35WXZpUinbo=`.

## Transaction

The only valid state sequence is:

`PREPARED -> AUTHOR_ATTESTED -> ASSETS_UPLOADED -> IMMUTABLE -> PAGES_MATERIALIZED -> BROWSER_VERIFIED`

The Pages workflow performs two publications:

1. It publishes a candidate whose 38 evidence rows may all validate, but whose
   public result is deliberately `CANDIDATE_PASS` with `ok=false` because the
   receipt is still `PAGES_MATERIALIZED`.
2. A newly created, service-worker-blocked Playwright Chromium context loads the
   network-visible candidate and checks 38/38 rows, seven same-origin evidence
   GETs, zero GitHub API calls, and zero console/page errors. It independently
   downloads the script and recomputes both SHA-256 and SRI.
3. The workflow uploads the browser receipt and screenshot, resolves the exact
   Actions artifact ID and archive digest, and appends them to the hash-chained
   receipt as `BROWSER_VERIFIED`.
4. It republishes the final artifact, requires public receipt byte equality,
   and repeats the fresh-browser check. Only this run may report `PASS`.

## Failure and recovery boundary

A crash before the browser receipt keeps the release at `PAGES_MATERIALIZED`;
reconciliation returns `RUN_BROWSER_VERIFICATION`. A browser result recorded by
the provider but not yet acknowledged is adopted only when its source, release,
script, Pages receipt, workflow, artifact, digest, context, engine, 38-row count,
and zero-error conditions all match. Any contradictory value is `AMBIGUOUS` and
fails closed. Existing immutable release assets and the author signature are not
rebuilt or repeated.

The final browser rerun is a postcondition of the Pages workflow, not another
author-controlled release mutation. The immutable browser artifact bound in the
receipt is the candidate observation that authorizes the state transition; the
second live run proves that the final network-visible bytes still satisfy it.

## Delivery receipt

Devpost project version 26 retains submission `1121568` at its original
`2026-08-01T11:22:19.310-04:00` Submitted timestamp and the existing 99.93-second
video. Its release-contract prose is intentionally tag-neutral. The exact tag,
source SHA, coordinator/Pages runs, artifact digests, script digest, Devpost
timestamp, video digest, and terminal receipt are resolved from the stable
[one-click verifier](https://yonghwan2161.github.io/continuum-memory-firewall/verify.html)
and immutable release assets instead of copied into mutable prose.

## Claim boundary

This closes the delivery/proof ordering gap. It proves that the exact public
judge program ran successfully in a fresh isolated Chromium context before the
release became terminal. It does not turn the static judge page into a live
CockroachDB or provider freshness oracle; those remain the authenticated online
verifier and scheduled monitoring responsibilities.

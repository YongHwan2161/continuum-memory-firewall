# Offline provider-story receipt closure v29

## Outcome

`hackathon-v29` is a fresh successor to immutable v28. It does not alter,
retry, or backfill v28. It fixes the only failure found by the required headed
browser audit: the provider-origin delivery row must compute the exact receipt
serialization used by Python, including one trailing LF after canonical JSON.

## Preserved v28 evidence

- release target: `73ba099bd19c58caab5dd84c303ae22061548d39`;
- coordinator run: `31706946192`;
- Pages run: `31707063340`;
- immutable envelope SHA-256:
  `2b3a1d7b882c51e96850c5e7a63ffd5715680bf9e550f86841acbbc93f678192`;
- capsule SHA-256:
  `c387b086a81fee4629e2adcb562aaac0026c0eae3d7be2844d02701e863cfae7`;
- online verifier: `45/45` PASS;
- headed zero-API browser: `37/38` PASS, with only the provider-story
  self-receipt row failing.

All video, caption, provider, CockroachDB, Devpost, release-asset, Sigstore, and
terminal-transaction comparisons were true. The false result was isolated to
`JSON.stringify(canonical(body))` versus the authoritative
`JSON.stringify(canonical(body)) + "\\n"` receipt input.

## Successor gates

v29 may publish only when:

1. the production browser helper includes the canonical LF;
2. a test executes that exact production JavaScript function with the retained
   `provider-origin-story-v1.json` and obtains receipt
   `f3cafd7db4ba6c4657f2751c022ab609612e84776fc39d3c656e17f6c57676e8`;
3. all Python, CockroachDB integration, MCP, cloud-readiness, JavaScript syntax,
   and release-contract tests pass;
4. the new immutable release and terminal Pages transaction bind the exact main
   SHA; and
5. a fresh headed browser reports all 38 rows PASS with zero GitHub API calls.

The v29 capsule will contain the complete 45-check v28 online result. The
current signed v29 envelope revalidates the delivery tuple, so the browser does
not double-count the provider check when reporting its effective check count.

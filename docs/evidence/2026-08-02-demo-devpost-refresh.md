# Demo and Devpost refresh evidence — 2026-08-02

## Outcome

The real-scale competition demo was rendered, reviewed, published, and bound to
the refreshed Devpost project receipt without exposing credentials.

- Public video: <https://youtu.be/H1hCZrC6ab8>
- Duration: `99.7` seconds
- File: `continuum-memory-firewall-demo-v2.mp4`
- File SHA-256:
  `ae63e843d6da1b532c59e6b85ed6a1cbf15e94aa6983f7cb748b08c0b51863fb`
- YouTube visibility: `Public`
- YouTube copyright check: no issues found
- Devpost project: <https://devpost.com/software/continuum-memory-firewall>
- Devpost project version: `10`
- Devpost updated at: `2026-08-02T02:34:11.143-04:00`
- Submission ID/status: `1121568` / `Submitted`

## Judge sequence

The 99.7-second video follows the competition-oriented path:

1. one-click read-only verifier;
2. verified caller to server-owned scope and matching SQL identity;
3. 60-query Titan retrieval and leakage metrics;
4. cross-scope attack denial by CockroachDB RLS;
5. natural 10k/50k CockroachDB vector-search plans and beam trade-off;
6. fail-closed Managed MCP key rotation.

## Claim boundary

The 10k/50k corpus is deterministic and non-sensitive. “Fresh connection” is
the first measured pass on a newly opened SQL connection; it is not described
as a physical CockroachDB Cloud cache flush. Raw runtime evidence and the video
binary remain outside Git; the repository retains bounded digests, receipts,
source, and the reproducible video builder.

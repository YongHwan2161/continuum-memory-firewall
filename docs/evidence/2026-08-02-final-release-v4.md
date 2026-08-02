# Final Devpost link closure and release v4

## Outcome

- Devpost project: <https://devpost.com/software/continuum-memory-firewall>
- Submission ID/status: `1121568` / `Submitted`
- Devpost project version: `13`
- Final project timestamp: `2026-08-02T05:05:28.543-04:00`
- Stable judge resolver:
  <https://yonghwan2161.github.io/continuum-memory-firewall/verify.html>
- Final immutable release: `hackathon-v4`

## Fixed-point correction

The final Devpost review found an old `hackathon-v2` URL in the project's
links. Replacing it with `hackathon-v3` would update the Devpost timestamp,
which would require a new release envelope; replacing it again with that new
tag would repeat the cycle.

The project links now contain only stable URLs: the read-only verifier, public
demo, and repository. The verifier resolves and validates the current immutable
release from `judge-verification.json`. This makes Devpost the mutable discovery
surface and the verifier the stable release resolver, so the final Devpost
timestamp can be bound once in `hackathon-v4` without another Devpost edit.

The submission requirements were re-read after the link correction and the
connector again returned `Submitted` for submission `1121568`. No credential,
token, connection string, AWS account identifier, or database row is included.

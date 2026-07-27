# Prior work and hackathon work boundary

This document records provenance so reviewers can distinguish pre-existing
concepts from implementation produced for this project.

## Pre-existing material

Before the current repository work, the project existed as:

- a problem framing for durable memory safety in long-running agents;
- an architecture concept separating candidate and canonical memory;
- planning notes about CockroachDB, optional AWS integration, cost, and
  submission strategy.

Those concepts informed the repository but were not themselves a working
transactional implementation.

## New repository work

The repository now contains the P1 transactional-authority implementation:

- deterministic promotion policy in `src/continuum/memory.py`;
- CockroachDB transaction, replay, and retry logic in
  `src/continuum/store.py`;
- packaged versioned schema, checksum history, renewable migration lease, and
  vector-index DDL in `src/continuum/migrations/`;
- synthetic live-database migration/promotion/retrieval smoke path;
- unit and real CockroachDB integration tests in `tests/`;
- GitHub Actions verification for the unit and integration paths;
- public proof-console deployment for reviewer-oriented policy scenarios;
- SSOT documentation for status, roadmap, architecture, transaction semantics,
  cost safety, and submission readiness.

## Honest attribution rule

Final submission language should describe the earlier work as problem discovery
and architecture exploration, and the repository implementation as the new
engineering artifact. Any future cloud deployment, MCP endpoint, retrieval
evaluation, or AWS integration must be added to this list only after its code and
verification evidence exist.

# Architecture and authority boundaries

## Problem statement

Persistent agent memory can preserve useful experience, but it can also preserve
stale, poisoned, cross-tenant, or conflicting information. Retrieval relevance
alone is insufficient for high-impact actions.

Continuum separates memory into four states:

1. **Observation** — untrusted input from a user, tool, model, or environment.
2. **Candidate** — a structured memory proposal stored for evaluation.
3. **Canonical** — a candidate accepted under an explicit policy and parent.
4. **Quarantined** — a rejected candidate retained as evidence.

## Authority model

| Component | May propose | May persist candidates | May accept canonical memory | May execute destructive actions |
|---|---:|---:|---:|---:|
| Bedrock model | Yes | Through bounded tools | No | No |
| MCP-connected agent | Yes | Yes | No | No |
| Continuum kernel | No | No | Yes | No |
| Human approver | Yes | Yes | Through policy | Yes |
| CockroachDB | No | Yes | Stores result | No |

The database provides persistence, transactions, constraints, and search. It
does not decide semantic validity. The model generates candidates. It does not
grant authority.

## Intended P1 flow

1. CloudWatch or a synthetic source emits an incident observation.
2. A Lambda worker retrieves bounded canonical context through CockroachDB MCP.
3. Distributed vector search returns similar incidents and runbooks within the
   same tenant and incident scope.
4. Bedrock proposes an observation or action as candidate memory.
5. The deterministic kernel validates scope, parent, provenance, expiry,
   approval, and resource ceilings.
6. Accepted candidates become immutable canonical events.
7. A unique `(incident_id, sequence_no)` constraint prevents two workers from
   committing the same transition position.
8. Rejected candidates remain queryable as evidence but cannot drive actions.

## Failure demonstrations

- terminate a worker after candidate creation but before acceptance
- resume with a new worker from the current canonical head
- submit two conflicting actions against the same expected head
- insert a semantically relevant but untrusted memory
- replay an accepted candidate
- attempt cross-tenant retrieval or promotion

## Honest non-claims

P0 is a local policy kernel and schema proposal. It is not yet a deployed
distributed system, a certified memory-poisoning defense, or proof of
multi-region survival.

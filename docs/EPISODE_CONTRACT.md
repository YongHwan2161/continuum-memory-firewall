# Episode contract

Continuum treats an agent episode as four independently auditable facts:

1. `agent_runs` records the server-owned tenant/incident scope, comparison arm,
   model identity, input digest, and terminal state;
2. `retrieved_citations` freezes the exact memory payload and digest that the
   model saw, rather than linking only to a mutable presentation layer;
3. `proposed_actions` records one allowlisted proposal with server-derived risk
   class and citations;
4. `outcome_evidence` records the provider receipt and its digest. A successful
   record requires a receipt, digest, and verification timestamp.

All four tables carry `(tenant_id, incident_id)` and database-native row-level
security. Composite foreign keys prevent a run or citation from being attached
to another scope.

## Model authority

The Bedrock Converse orchestrator uses client-side tool calling. The model can
request only:

- `search_memory(query, limit)`;
- `fetch_memory(citation_handle)`, limited to an opaque server-issued handle
  returned by the current run's search;
- action-specific proposal tools such as `propose_restart_service(...)`, each
  generated from one server-maintained action policy.

No tool accepts tenant or incident identifiers. The server injects scope into
the retrieval adapter. A `propose_*` tool only writes a proposal; it cannot
call a provider, enqueue delivery, approve destructive work, record success,
or promote canonical memory. Its name fixes the action type and its closed
parameter schema omits every field owned by another action.

Search results never expose database memory IDs to the model. For each current
search hit the server issues an unpredictable `cit_*` handle, keeps the
handle-to-memory mapping inside the episode, and rebuilds every fetch and
proposal schema with an `enum` containing exactly those handles. Proposal tools
accept `citation_handles`, not memory IDs; the server resolves accepted handles
back to durable memory IDs only after schema and phase validation. With no hits,
the proposal schema permits zero handles. A fabricated, previous-run, duplicated,
or otherwise unissued handle fails closed even if a provider ignores JSON Schema.

Tool availability is an explicit episode phase machine, not one broad
allowlist. A memory arm receives only `search_memory` on its first turn. An
empty search closes retrieval and exposes only action-specific `propose_*`
tools; a non-empty search exposes `fetch_memory` and those proposal tools;
after one fetch, only the proposal tools remain. Repeated search/fetch and any tool not exposed in the
current phase fail closed. This prevents an unconstrained model choice from
turning a cold start into an invalid fetch loop.

## Fail-closed limits

- eight model turns and sixteen tool calls per run by default;
- five search hits per call and twenty citations per episode;
- 32 KiB agent input, 24 KiB tool result, and 16 KiB action parameters;
- memory-enabled proposals with hits must cite a server handle issued by that
  same run;
- stateless proposals cannot cite memory;
- unknown tools, action types, parameters, scope fields, or pre-search fetches
  terminate the run as failed.

Rejected runs carry a bounded stable failure code plus attempted model-turn and
tool-call counts. Provider exception text is not copied into evaluation output.

The external-effect and promotion boundary is specified separately in
`TRANSACTION_MODEL.md`; a model response is never outcome evidence.

## Outcome-gated promotion

An allowlisted proposal still requires a separate approval transition. Only a
`succeeded` provider outcome with a receipt ID, canonical receipt digest, and
verification timestamp can create a `tool`-sourced candidate and canonical
memory. Outcome evidence, candidate insertion, incident-head compare-and-set,
canonical insertion, and run completion occur in one SERIALIZABLE transaction.
Failed and `ambiguous` outcomes complete the run without creating a candidate.
The unique `(provider, provider_receipt_id)` index prevents one receipt from
authorizing more than one episode.

## Transactional outbox and crash states

An approved proposal is enqueued in the same CockroachDB SERIALIZABLE
transaction that moves the proposal and run to `enqueued`. The action payload
is derived from the durable proposal; callers cannot substitute another body.
The worker commits `dispatching` before it crosses the provider boundary and
commits the provider response before it acknowledges the episode.

- A crash before send expires back to `pending`; no provider effect exists.
- Each outbox row freezes a capability manifest: `supports_idempotency`,
  `receipt_lookup`, and a bounded `reconciliation_timeout`. A worker whose live
  adapter differs from that durable manifest is rejected before dispatch.
- A crash after send first uses receipt lookup when declared. Before the
  timeout it remains `dispatching`; after the timeout it resends only when the
  frozen manifest guarantees idempotency.
- Without a found receipt or provider idempotency, an after-send crash becomes
  `ambiguous`; the worker never blindly resends and no canonical memory is
  promoted.
- A crash after receipt persistence but before acknowledgement reuses the
  durable receipt and the idempotent outcome-promotion transaction.

The AWS sandbox adapter crosses a real Lambda boundary and stores receipts in
an encrypted, TTL-bounded DynamoDB table. Its manifest declares idempotent
send, receipt lookup, and a 30-second reconciliation timeout. The adapter is
non-production and non-effecting; this does not claim generic exactly-once
semantics for arbitrary external systems.

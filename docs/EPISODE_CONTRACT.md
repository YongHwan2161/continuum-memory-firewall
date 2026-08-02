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
- `fetch_memory(memory_id)`, limited to an ID returned by the current run's
  search;
- `propose_action(...)`, limited to server-maintained action policies.

No tool accepts tenant or incident identifiers. The server injects scope into
the retrieval adapter. `propose_action` only writes a proposal; it cannot call a
provider, enqueue delivery, approve destructive work, record success, or
promote canonical memory.

## Fail-closed limits

- eight model turns and sixteen tool calls per run by default;
- five search hits per call and twenty citations per episode;
- 32 KiB agent input, 24 KiB tool result, and 16 KiB action parameters;
- memory-enabled proposals must cite a memory returned in the same run;
- stateless proposals cannot cite memory;
- unknown tools, action types, parameters, scope fields, or pre-search fetches
  terminate the run as failed.

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

# Demo narration v2

Continuum Memory Firewall gives long-running agents durable memory without
giving semantic similarity the power to decide authority.

The judge starts here, with one public, read-only verifier. It checks the exact
GitHub workflow and deployed source, the live MCP health endpoint, the submitted
Devpost receipt, the evaluation bundle, and the absence of temporary migration
capabilities. No judge credential, database password, or write permission is
required.

The authorization chain begins with a five-minute Cognito token. After the
caller is cryptographically verified, an audited and versioned tenant binding
selects one server-owned tenant and incident. That binding selects a
deterministic, no-bypass SQL role. CockroachDB row-level security independently
enforces the same scope at the database row.

Retrieval quality is measured, not assumed. Amazon Titan Text Embeddings version
two ran sixty adversarial and similar-meaning queries across paraphrase, terse,
typo, negation, misleading-scope, and multi-intent variants. Recall at three was
ninety-eight point three percent, Recall at five was one hundred percent, and
cross-scope leakage was zero.

Here is the attack boundary. Even a foreign memory with a perfect semantic
match remains invisible. Caller binding, SQL identity, and row policy all have
to agree. Similarity never becomes authorization.

The same retrieval shape was then tested at ten thousand and fifty thousand
non-sensitive, five-hundred-and-twelve-dimensional vectors. Exact primary-index
scans provide ground truth. CockroachDB naturally selects its prefixed vector
search operator, while beam sizes one, thirty-two, one hundred twenty-eight,
and five hundred twelve expose the
real Recall and latency trade-off. Every query returns zero foreign-scope rows.

Operational credentials also fail closed. A replacement key is staged without
appearing in logs, written to AWS Secrets Manager, and held beyond the Lambda
cache window. Read tools must pass and the write tool must remain denied before
the old key is retired. If validation fails, the prior AWS secret is restored.

Continuum turns agent memory into an auditable database authority system. A
model may propose. The database grants authority. Long-running agents need
memory. Production agents need a memory firewall.

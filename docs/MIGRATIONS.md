# Database migration contract

This document is the single source of truth for Continuum's CockroachDB schema
migration format, execution guarantees, failure semantics, and authoring rules.
Cloud account operations belong in
[CLOUD_DEPLOYMENT_RUNBOOK.md](CLOUD_DEPLOYMENT_RUNBOOK.md); current evidence
belongs in [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Why the bootstrap schema was removed

`CREATE TABLE IF NOT EXISTS` checks only whether a table name exists. It does not
prove that an existing table has the expected columns, constraints, or indexes.
The former `db/schema.sql` could initialize an empty database, but could not
reliably distinguish a current schema from an older or partially applied one.

The authoritative schema is now the ordered SQL set in
`src/continuum/migrations/`. The package includes these files so the same
artifact is used by local development, CI, and a live deployment.

## File contract

Each migration:

- is named `NNNN_lowercase_name.sql`;
- has a contiguous version starting at `0001`;
- contains exactly one SQL statement;
- is safe to execute again if its metadata write was interrupted;
- performs one online schema change and ends with a semicolon;
- is immutable after it has been applied anywhere;
- is checksummed and executed after newline normalization to the historical
  CRLF representation, so Windows and Linux checkouts produce the same bytes.

CockroachDB recommends executing schema-changing DDL as individual implicit
transactions. A single statement per migration avoids presenting multiple DDL
changes and a metadata write as one transaction when CockroachDB cannot
guarantee that atomicity.

Never edit an applied file. Add the next numbered migration. Destructive changes
such as dropping a column require an explicit expand/migrate/contract plan and
must not be mixed with an unrelated schema change.

## Runtime guarantees

`continuum-migrate` provides:

1. ordered discovery with gap and filename validation;
2. a SHA-256 checksum for the canonical CRLF migration bytes;
3. `continuum_schema_migrations` history;
4. a durable pre-DDL intent in `continuum_migration_intents`, so a process
   stopped between DDL success and history recording can safely resume;
5. a renewable database lease in `continuum_migration_lock`;
6. a heartbeat while a long-running schema job is active;
7. bounded retry of SQLSTATE `40001`;
8. fail-closed handling of CockroachDB `XXA00`, which requires operator
   inspection because state may be uncertain;
9. post-apply validation of required tables, columns, indexes, and composite
   tenant/incident foreign keys;
10. rejection of cleartext remote connections unless `sslmode=verify-full`.

DDL and its history insert are intentionally separate. If the process stops
after successful DDL but before recording history, the next run safely replays
the idempotent statement identified by the durable intent, then records its
checksum. A pre-existing product table without either migration history or an
intent remains an explicit-adoption case.

The caller-scoped SQL login is a separate one-time bootstrap boundary. Its
creator temporarily needs only `CREATEROLE` and `CREATELOGIN`; those options
must be removed immediately after the first successful cutover. Later deploys
recognize the deterministic scope login in the runtime secret and verify its
RLS negative tests without recreating the login or requiring either option.

Migrations `0012` through `0015` add the tenant control plane as four separate
online schema changes: the current caller binding, its scope index, the
append-only audit history, and its caller/version index. A binding stores the
deterministic scope SQL role as well as tenant and incident IDs. The runtime
resolver accepts only an active, positive-version binding whose role can be
recomputed from those IDs; a self-asserted tenant claim never selects a role.

## Existing unmanaged schema

The migrator never silently marks pre-existing application tables as current.
The first normal run fails with `MigrationAdoptionError`.

For a database previously created from the final P2 `db/schema.sql`:

1. back up or export the synthetic evidence that must be preserved;
2. ensure no other deployment is changing the schema;
3. run the normal migrator and confirm it refuses unmanaged tables;
4. inspect tables, indexes, and constraints;
5. explicitly run:

   ```bash
   PYTHONPATH=src python -m continuum.migrate --adopt-existing
   ```

Adoption validates the expected P2 columns, indexes, and composite scope foreign
keys before recording checksums. An older P1 or partial schema fails validation
and requires a purpose-built forward migration; it must not be forced into the
baseline.

## Commands

Install the CockroachDB dependency and set the URL through the environment so it
does not appear as a command-line argument:

```bash
python -m pip install -e ".[cockroach]"
read -rsp 'CockroachDB SQL URL: ' CONTINUUM_DATABASE_URL
printf '\n'
export CONTINUUM_DATABASE_URL
make migrate
```

Run the synthetic end-to-end database smoke test:

```bash
./scripts/smoke_live_database.sh --apply
```

The default smoke test:

- applies or validates all migrations;
- creates random synthetic tenant, incident, and candidate IDs;
- promotes the candidate transactionally;
- writes a 512-dimensional test embedding;
- performs tenant-and-incident-scoped retrieval;
- verifies retrieval audit and fetch;
- deletes only the generated rows;
- prints non-secret evidence as JSON.

Use `--retain` only for a dedicated hackathon cluster when reviewer-visible
evidence must remain:

```bash
./scripts/smoke_live_database.sh --apply --retain
```

The output contains identifiers but never prints the database URL or password.

## Failure response

| Failure | Required response |
|---|---|
| Checksum drift | restore the committed file; never update the database checksum to hide drift. A checkout-only LF/CRLF difference is normalized before comparison. |
| Active lease | wait for the other migration; do not bypass it |
| Expired lease after a crash | inspect CockroachDB schema jobs, then rerun the idempotent migration |
| `XXA00` uncertain state | inspect `SHOW JOBS` and the affected object before any retry |
| Adoption validation failure | create a specific forward migration from the observed schema |
| Remote TLS rejection | use the CockroachDB CA and `sslmode=verify-full` |

CockroachDB documents online schema changes as background jobs and warns that
multi-statement DDL transactions do not have general full atomicity guarantees:
<https://www.cockroachlabs.com/docs/stable/online-schema-changes>.

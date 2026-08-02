# Concurrent-agent pressure evidence — 2026-08-02

## Outcome

The participant CockroachDB cluster passed a bounded mixed workload at 10, 25,
and 50 concurrent agents. A content-equivalent JSON mirror is public at
`public-demo/evidence/agent-pressure.json`; both binary digests are recorded
below.

- GitHub Actions run: `30739691518`
- Workflow head: `c8478b65b13a09c6586fba3000154a9b29f62868`
- Artifact ID: `8830851472`
- Artifact SHA-256:
  `50b742008025aeb510bb0e150e4ca93679977ad9bbc03a1a2ffef639dda92de9`
- Public JSON mirror SHA-256 (same JSON payload without the artifact's terminal
  newline):
  `8ae242a6d793cb56f4b8dfb7ae792b1160124827bb723b124d1aeacc37b9acb8`
- Temporary secret-read capability absent after the run: `true`
- Run-owned application rows retained: `0`

## Workload

Every agent performed ten operations: seven ANN reads over the retained 50k
non-sensitive corpus, two trusted memory promotions, and one shared action
claim. The application pool was capped at 20 connections even for 50 agents.

| Agents | Ops | Throughput | p50 | p95 | p99 | Action owner |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 46.560/s | 188.221 ms | 448.126 ms | 544.233 ms | 1 |
| 25 | 250 | 80.400/s | 295.451 ms | 617.880 ms | 687.242 ms | 1 |
| 50 | 500 | 69.938/s | 695.983 ms | 1228.640 ms | 1342.502 ms | 1 |

All levels had zero worker errors, zero cross-scope rows, exactly one claimed
action, N-1 duplicate action results, and two accepted promotions per agent.

## Recovery boundary

After each level the client connection pool was deliberately torn down and
rebuilt. Time to the first successful vector result was 126.481 ms, 136.183 ms,
and 117.960 ms. This is evidence for bounded client-pool recovery; it is not a
CockroachDB node-failover claim.

## Insight

Throughput peaked at 25 agents and decreased at 50 while p95 nearly doubled.
The pool remained correct, but 599 of 603 connection requests queued in the
50-agent window. The next performance improvement should therefore be
admission control and per-operation concurrency budgets, not a larger
unbounded SQL pool.

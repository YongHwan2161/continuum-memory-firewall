# Public proof console artifact

This directory is the static, logged-out GitHub Pages build of the Continuum
Memory Firewall reviewer console.

Source UI commit: `1e3c31ea4f5d0d1ebd4304bf4b68000449c6cf4f`

The page is an executable browser simulation of the deterministic policy and
replay contracts. It does not connect to the participant CockroachDB Cloud
cluster and must not be cited as live managed-database evidence.

`verify.html` is a separate read-only judge path. It loads the exact live
evidence receipt in `evidence/judge-verification.json`, checks the public GitHub
Actions run and MCP health endpoint, and performs no authenticated or mutating
request. The live retrieval and RLS claims remain bound to the cited workflow,
not to browser simulation code.

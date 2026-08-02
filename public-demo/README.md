# Public proof console artifact

This directory is the maintainable, static, logged-out GitHub Pages source for
the Continuum Memory Firewall reviewer console. `index.html`, `app.css`, and
`app.js` are the deployable source; the historical generated bundles under
`assets/` are retained only for their local font files.

The page presents evidence and performs read-only public health checks. It does
not receive a judge credential, connect directly to CockroachDB, or mutate any
application or submission state.

`verify.html` is a separate read-only judge path. It loads the exact live
evidence receipt in `evidence/judge-verification.json`, checks the public GitHub
Actions run and MCP health endpoint, and performs no authenticated or mutating
request. The live retrieval and RLS claims remain bound to the cited workflow,
not to browser simulation code.

`evidence/vector-scale.json` is the frozen output of the fixed-egress 10k/50k
benchmark workflow. Its first-pass latency includes a fresh connection but is
not described as a physical server-cache flush.

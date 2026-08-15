# Preserved v34 final-browser propagation failure

`hackathon-v34` is an immutable release whose Pages delivery epoch failed. It
is not retried, backfilled, or promoted to terminal PASS.

- Release target: `ccc42cb52a8b503d93ce0a98f92f1d41fe428446`
- Release workflow run: `31861288106` (`success`)
- Pages workflow run: `31861327695` (`failure`)
- Failure step: `Re-run the one-click judge against the final deployment`
- Candidate browser: PASS
- Transaction advancement: `BROWSER_VERIFIED`
- Final public terminal receipt: verified before the failing browser step

The first final browser context observed a forbidden request or console error
immediately after the second Pages deployment. A subsequent independent
in-app Browser session loaded the same public URL, clicked the verifier, and
rendered `PASS · browser verified · 0 GitHub API requests`. This identifies a
bounded Pages propagation race, but the later observation does not rewrite the
failed workflow epoch.

The v35 successor keeps every final browser assertion unchanged and retries a
fresh final browser context up to twelve times with five-second spacing. The
workflow still terminates unless one complete attempt has 39/39 PASS, terminal
`BROWSER_VERIFIED`, zero GitHub API requests, and zero console errors.

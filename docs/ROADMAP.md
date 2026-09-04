# Roadmap / deferred ideas

## Browser auto-commit via a GitHub PAT (deferred - do later)

**Goal:** let the app's "Add transaction" / "Import CSV" flow commit the updated
`config/holdings.csv` straight to GitHub, so a change goes live with no local
step at all. After the commit, the existing GitHub Action already recomputes
(accurate FX / average cost / realized P&L) and redeploys - that part needs no
change and no token.

**How it would work:**
- A settings field where the user pastes their own **fine-grained PAT**, scoped
  to **this repo only**, permission **Contents: write**. Stored in the browser's
  `localStorage` (never in the source, never committed).
- On commit: `PUT /repos/{owner}/{repo}/contents/config/holdings.csv` with the
  new content (base64) + the file's current `sha`. The push triggers CI.
- Owner/repo can be read from the Pages URL or a small config value.

**Why it's deferred / the hard constraint:**
- A write-scoped token must **never** live in a publicly deployed page - anyone
  could lift it from a shared/hosted build and push to the repo. This directly
  conflicts with the project's "secrets never reach the browser" principle
  (see `docs/adr/0001`).
- So this is only defensible for a **local-only** build the user runs on their
  own machine, with a token they enter themselves. It should be off by default,
  clearly labelled local-only, and ideally compiled out of the deployed bundle.

**Safer alternatives already shipped (no token):**
- `python scripts/add_lot.py ... --rebuild` - edits the CSV and rebuilds in one
  command, then prints the `git commit && git push` to publish.
- CI recompute + deploy on every push to `config/` (built-in `GITHUB_TOKEN`).

**Decision:** revisit when there's a concrete need for zero-local-step edits, and
only as a local-only, opt-in feature with the token handled entirely by the user.

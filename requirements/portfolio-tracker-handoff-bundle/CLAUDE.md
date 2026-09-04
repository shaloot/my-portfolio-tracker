# Working notes for the coding agent

You're building the app specified in `REQUIREMENTS.md`. A reference
implementation is in `reference-implementation.zip` — consult it to confirm
decisions and the JSON data contract, but write and test fresh code here, where
live data fetching works (the reference was built in a sandbox that couldn't
reach Yahoo/NSE).

## How to work
- Build the whole thing end-to-end in one pass, then hand back a runnable state
  for review. Don't stop for per-step approval; pause only for a genuine blocker.
- Validate as you go: get `--mock` producing valid JSON before building the
  frontend, then do a live run and inspect real prices.
- Keep the design restrained — the waterline chart is the one bold element.

## Ground rules (from the user's principles)
- **Never run git, pushes, deploys, key registration, or secret-setting for the
  user (principle 9).** When an external step is needed, give exact copy-paste
  commands (or click-by-click UI steps) and, after each, explain in plain
  language what it did, what to expect, and where to confirm it worked. The
  app's *own* CI committing data / deploying is fine — that's automation, not
  you acting for them.
- Open-source + free tiers only. Flag any paid dependency before adding it.
- No secrets in client code. The only key in the whole system is an optional
  Twelve Data key, and it lives in CI secrets, used at build time only.
- Providers are swappable by env var; every provider choice gets an ADR.
- **Pin dependency versions** and keep the offline `--mock` path working — the
  project must build and run from a clean checkout with no accounts (principle 12).

## Definition of done
Everything in `REQUIREMENTS.md` §8. The parts that matter most here:
- **Live fetch (only you can verify this):** run `python scripts/fetch.py`
  against real yfinance + RSS; confirm Indian (`.NS`) and US tickers both
  resolve, and that a deliberately-bad ticker degrades to a "stale" row instead
  of crashing the build (principle 13).
- **Reproducible:** `pip install -r scripts/requirements.txt` resolves with
  pinned versions; `python scripts/fetch.py --mock` runs with no network/keys.
- **UI floor (principle 14):** responsive to mobile, visible keyboard focus,
  reduced-motion respected — check these before calling it done.

## Don't
- Don't pick Alpha Vantage for prices (25 req/day — verified, rejected).
- Don't add a database or an always-on server.
- Don't fetch from external APIs in the browser — all fetching is build-time.
- Don't let one bad symbol or a dead feed break the whole build (principle 13).
- Don't reproduce large chunks of the reference verbatim without understanding
  them; if you diverge, update the ADRs to match.

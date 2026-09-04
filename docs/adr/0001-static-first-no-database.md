# ADR 0001 - Static-first, and no database

**Status:** Accepted · **Date:** 2026-07-11

## Context
We track an end-of-day portfolio (prices, P&L, charts, news). The data changes
at most once per trading day. Two questions follow: do we need an always-on
backend, and do we need a database?

## Decision
**No backend, no database.** A single scheduled GitHub Action fetches data once
per day, computes everything, and writes three static JSON files
(`portfolio.json`, `history.json`, `news.json`). The Action commits those back
to the repo and publishes the site to GitHub Pages. The browser only ever reads
flat files.

The "database" is Git itself: `history.json` gets one point appended per day and
committed, giving a versioned, diffable record with zero infrastructure.

## Alternatives considered
- **Serverless function + hosted DB (Supabase / Neon free tier).** Real free
  tiers exist, but each adds a moving part, a second dashboard, and another place
  for secrets to leak. Rejected - nothing here needs request-time compute.
- **Client-side fetch from the browser.** Would expose provider limits/keys to
  every visitor and couple cost to traffic. Rejected (violates principles 5, 8).

## Consequences
- API usage is a function of the daily cron, not of visitor count, so it is
  trivially free no matter how many people open the page.
- Data is at most ~1 day stale. Acceptable for an EOD tracker; stated in the
  page footer.
- Reset the history curve by deleting `history.json`; the next run backfills it
  from each holding's own price history (see `core/compute.backfill_history`).
- Since the curve is an appended series, a change of data *scale* (switching mock
  <-> live, or a large config change) would append a point far from the rest and
  draw a false vertical spike. `fetch.py` guards against this: if today's total
  differs from the last point by more than ~100%, it rebuilds the whole curve
  from backfill instead of appending. Normal day-to-day moves (single digits) are
  unaffected.

# Portfolio Tracker — Build Requirements

A spec for building a free, open, end-of-day portfolio tracker. Build the app to
satisfy this document. A **reference implementation** ships alongside this bundle
(`reference-implementation.zip`) — consult it to confirm decisions and data
shapes, but you may write fresh code in your own environment (where live data
fetching actually works). Per principle 11, this bundle is the deliverable and
the reference is an optional appendix.

---

## 1. What we're building
A static website that tracks a personal portfolio of **Indian (NSE/BSE) + US
equities**, refreshed **once per day (end-of-day)**, showing total value, P&L,
day change, per-holding detail with charts, allocation, and news. No backend, no
database, no paid API.

## 2. Operating principles (hard constraints)
The full text lives in the project's build-instructions doc; the load-bearing ones:
1. **Open & free only.** OSS + free tiers. Flag any paid dependency first.
2. **Free-tier-driven.** For each external service, ≥2 alternatives with *current*
   (verify — they change) free-tier limits; default to the most liberal.
3. **Three places must agree:** env (selects provider) · code (adapter behind a
   fixed interface) · docs (an ADR with alternatives + rationale). Swap = config, not rewrite.
4. **Static-first, server-never.** Pre-rendered output refreshed by scheduled CI.
5. **Secrets never reach the browser.** Keys live in CI secrets, used at build time only.
6. **Free on GitHub with CI/CD** that rebuilds on every change. Public repo.
7. **Databases: ask if one is needed at all** before adding one.
8. **Stay in free tiers by design** (central scheduled fetch, caching, guards).
9. **Never run git/deploy/keys on the user's behalf.** Copy-paste commands with a
   plain-language "what this did" after each. (App's own CI committing/deploying is fine.)
10. **Build a reference implementation end-to-end in one pass** to prove the decisions.
11. **Deliver as a handoff bundle for a coding agent** (this doc + CLAUDE.md + reference).
12. **Reproducible and offline-testable.** Pin dependency versions; ship an offline/
    dry-run mode (mock data, no network, no keys) so it builds and runs from a clean
    checkout with no accounts.
13. **Fail safe; degrade gracefully.** One bad input or dead source must never break
    the whole build/output — isolate, flag visibly, continue.
14. **Quality floor for any UI:** responsive to mobile, keyboard-accessible with
    visible focus, respects reduced-motion — unprompted.

## 3. Scope & features
- Holdings defined in a **config file the user edits** (`config/holdings.json`):
  `{ symbol, name, market: "IN"|"US", quantity, avg_cost }`. Ticker is plain
  (`RELIANCE`, `AAPL`); market-specific suffixes are added in code.
- One **base currency** (default INR); mixed-currency holdings converted for totals.
- **Views:** total value · today's change (abs + %) · total P&L (abs + %) · invested
  cost · a hero portfolio-value chart · per-holding table (qty, avg cost, last, day %,
  trend sparkline, value, P&L, weight) · allocation by market · market + per-holding news.

## 4. Data providers — DECIDED (limits verified 2026-07; re-verify if building later)
Do not re-research from scratch; these were checked. All defaults are **keyless**.

| Concern | Default | Alternatives (free tier) | Rejected |
|---|---|---|---|
| IN prices | `yfinance` (keyless, `.NS`) | `bhavcopy` via `jugaad-data` (official NSE, keyless, unlimited) | — |
| US prices | `yfinance` (keyless) | `twelvedata` (800 req/day, **keyed** — the one CI secret) | — |
| News | `rss` (feeds + Google News RSS, keyless, no quota) | — | NewsAPI (100/day, non-commercial) |
| FX | `yfinance` (`USDINR=X`) | `exchangerate_host` (keyless) | Alpha Vantage FX (shares 25/day) |

**Alpha Vantage is rejected for prices — free tier is 25 requests/day (a demo).**
Each concern is one adapter behind a fixed interface, selected by env var
(`PRICE_PROVIDER_IN`, `PRICE_PROVIDER_US`, `NEWS_PROVIDER`, `FX_PROVIDER`), each
documented in an ADR. **Pin versions** (verified 2026-07): `yfinance==1.5.1`,
`feedparser==6.0.12`, `jugaad-data==0.33.1`; twelvedata adapter uses stdlib only.

## 5. Architecture
- **Pipeline** (`scripts/fetch.py` + `core/` math & registry + `providers/` adapters):
  loads config → fetches prices/FX/news via selected adapters → computes P&L →
  writes `data/portfolio.json`, `data/history.json`, `data/news.json`.
- **No database** (principle 7): git *is* the store. `history.json` gets one appended
  point per day, committed by CI. On first run (empty history), **backfill** the value
  curve from each holding's own price history so the first deploy shows a real chart.
- **Offline mode** (principle 12): a `--mock` flag on the pipeline yields deterministic
  data with no network and no keys, for tests and preview.
- **Frontend** (`site/`): plain HTML/CSS/JS, reads the three JSON files, no framework
  required. A build step assembles `site/* + data/*` into `public/` (identical locally
  and in CI so preview == prod).
- **CI/CD** (`.github/workflows/`): daily cron (after US close, ~22:30 UTC weekdays) +
  on config/site/script changes + manual dispatch. Fetches, commits refreshed `data/`
  back, deploys `public/` to GitHub Pages. Keyless unless the user opts into twelvedata.

## 6. Data contract (frontend depends on these shapes)
```
portfolio.json: { generated_at, base_currency, fx:{CCY:rate},
  totals:{ value_base, cost_base, pnl_base, pnl_pct, day_base, day_pct },
  holdings:[ { symbol, name, market, currency, quantity, avg_cost, last, prev_close,
    value_native, value_base, cost_base, pnl_native, pnl_pct, day_native, day_pct,
    spark:[..closes..], weight_pct, stale, error } ] }
history.json:  { base_currency, generated_at, series:[ { date, value_base, cost_base } ] }
news.json:     { generated_at, market:[ {title,url,source,published} ],
                 by_symbol:{ SYMBOL:[ {title,url,source,published,symbol} ] } }
```

## 7. Design direction
A cool, precise **"quant ledger"** look — deliberately *not* the cream/serif/terracotta
or dark-neon defaults. Space Grotesk (display) + Inter (body) + JetBrains Mono
(tabular figures). Indigo (#2E3A8C) as the brand accent; **green/red reserved strictly
for P&L semantics**, never decoration. Tabular numerals everywhere figures align.
**Signature element:** a *cost-basis waterline* on the hero chart — a dashed horizontal
line at what you paid; the value area fills **green above / red below** it, and the line
+ endpoint take the color of the ending position. Spend the boldness there; keep
everything else quiet.

## 8. Definition of done (acceptance criteria)
- **Offline (12):** `python scripts/fetch.py --mock` writes all three JSON files with no
  network/keys, from a clean checkout; deps are pinned and `pip install -r` resolves.
- **Live:** `python scripts/fetch.py` fetches real EOD prices. **← test in-environment;
  the reference couldn't reach Yahoo/NSE.** Confirm `.NS` and US tickers both resolve.
- **Graceful degradation (13):** a bad ticker becomes a "stale" row, and an FX failure
  falls back without crashing — the build always completes and flags the failure visibly.
- **Render:** correct currency formatting (INR lakh grouping), all holdings, the hero
  waterline chart (verify the **crossing case**: green-above flips to red-below),
  per-row sparklines, allocation, and news.
- **UI floor (14):** responsive to mobile, visible keyboard focus, reduced-motion respected.
- **Swap:** changing one env var switches a provider (prove one, e.g. IN→bhavcopy).
- **Docs:** four ADRs (static-first, price providers, news, FX) with alternatives + limits;
  README with copy-paste local-run and GitHub-Pages-deploy steps, each with a
  plain-language "what this did" (principle 9).
- **Deploy:** free, public repo, GitHub Actions; keyless by default.

## 9. Suggested build order
config → interfaces → compute (+ tests) → registry → providers (mock first) →
fetch.py → run `--mock` and validate the JSON contract → frontend against that JSON →
headless render check (incl. chart crossing case) → CI workflow → ADRs + README →
live run → package.

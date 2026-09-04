# ADR 0002 - Price provider selection

**Status:** Accepted · **Date:** 2026-07-11 · Limits verified 2026-07-11

## Context
We hold both Indian (NSE/BSE) and US equities and need end-of-day closes plus a
short price history, on free tiers, ideally keyless.

## Options and current free-tier limits

| Provider | Markets | Key? | Free tier (verified Jul 2026) | Notes |
|---|---|---|---|---|
| **yfinance** | IN + US | No | No formal limit (unofficial, scrapes Yahoo) | Simplest; can break without notice |
| **NSE bhavcopy** (via `jugaad-data`) | IN only | No | Unlimited, official EOD | Library absorbs NSE URL/cookie churn |
| **Twelve Data** | IN + US | Yes | 800 req/day, 8 req/min, delayed EOD | Reliable; needs a key |
| FMP | US (+intl) | Yes | 250 req/day | Rejected: tighter than Twelve Data |
| Alpha Vantage | IN + US | Yes | **25 req/day** | Rejected: a demo, not a tier |

## Decision
Two switches (`PRICE_PROVIDER_IN`, `PRICE_PROVIDER_US`); every adapter sits
behind one `PriceProvider` interface (`core/interfaces.py`).

- **Default IN = `yfinance`; default US = `yfinance`.** Most liberal *and*
  keyless, so the whole app runs with zero secrets out of the box.
- **`bhavcopy`** is the recommended IN upgrade for official NSE data. Also
  keyless. Switch with `PRICE_PROVIDER_IN=bhavcopy`.
- **`twelvedata`** is the documented US fallback for when yfinance is flaky. It
  is the only option needing a key, which lives in CI secrets (ADR 0001,
  principle 5). Switch with `PRICE_PROVIDER_US=twelvedata` + `TWELVEDATA_API_KEY`.

Alpha Vantage's 25/day makes it unusable for a multi-holding portfolio and is
recorded here only as a rejected alternative (do not use it for prices).

## Verified live (2026-07-11, this build)
- `yfinance`: `.NS` (RELIANCE, INFY) and US (AAPL, MSFT) all resolve; a bad
  ticker returns `ok=False` and renders as a "stale" row rather than crashing.
- `bhavcopy`: RELIANCE resolved to the same close as yfinance. Note: `jugaad-data
  0.33.1` creates its disk cache with a non-idempotent `os.makedirs` guarded by a
  check-then-create race, which trips `[Errno 17] File exists` when several
  symbols are fetched in a loop. The adapter (`providers/price_bhavcopy.py`)
  pre-creates that cache directory with `exist_ok=True` so the library never
  hits its racy branch.

## Consequences
Swapping is a repo Variable change, e.g. `PRICE_PROVIDER_US=twelvedata` +
`TWELVEDATA_API_KEY` secret. No code changes. If Yahoo breaks, flip
`PRICE_PROVIDER_IN=bhavcopy` and `PRICE_PROVIDER_US=twelvedata`, then redeploy.

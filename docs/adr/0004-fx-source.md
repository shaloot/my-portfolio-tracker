# ADR 0004 - FX source for base-currency conversion

**Status:** Accepted · **Date:** 2026-07-11

## Context
Holdings span INR and USD; totals must be shown in one base currency
(`base_currency` in `settings.json`, default INR). We need one FX rate per
non-base currency, once per daily build.

## Options
| Option | Key? | Notes |
|---|---|---|
| **yfinance** (`USDINR=X`) | No | Same dependency as the default price adapter |
| **open.er-api.com** | No | Open FX API, keyless; used as the `exchangerate_host` fallback |
| exchangerate.host | Yes* | *Now gates its endpoints behind a free access key (verified 2026-07), so it is no longer keyless - superseded by open.er-api.com below |
| Alpha Vantage FX | Yes | Rejected: shares the 25/day cap |

## Decision
`FX_PROVIDER=yfinance` (default), since it reuses an existing keyless dependency.
`exchangerate_host` is the keyless HTTP fallback behind the same `FxProvider`
interface. Note: the service originally chosen (exchangerate.host) began
requiring an access key, so that adapter now targets **open.er-api.com**, which
is still keyless and returns the same shape of data. The env id stays
`exchangerate_host` for continuity with older configs.

## Verified live (2026-07-11, this build)
- yfinance FX resolved `1 USD = 95.37 INR`.
- Forced-failure path: with an unresolvable base currency, the pipeline logged
  the failure and fell back to a `1.0` rate rather than crashing; native-currency
  figures stay correct regardless (principle 13).

## Historical FX for lot-based cost basis
When a holding lists dated purchase `lots` (see `config/holdings.csv`), the cost
basis values each lot at the FX rate **on its purchase date**, so base-currency
P&L captures currency moves, not just price moves. This uses the optional
`FxProvider.get_rate_series(base, quote, start_date)` method:
- **yfinance** implements it (historical `USDINR=X` closes) - verified live
  2026-07: 510 daily points fetched, lot cost booked at the ~84-86 purchase-date
  rate vs the ~95 spot rate.
- **exchangerate_host** (open.er-api.com) has no free historical endpoint, so it
  inherits the base `{}` default and lot cost falls back to today's rate.
- Undated/legacy holdings (`quantity` + `avg_cost`) always use today's rate, as
  before - so this is fully backward compatible.

## Consequences
- One spot FX call per non-base currency present, plus one historical-series call
  per non-base currency that has dated lots, once per build.
- If FX fails, `fetch.py` catches it and substitutes `1.0` (spot) or today's rate
  (per-lot), so the build always completes and the failure is visible in the logs.
- Only currencies actually held are fetched.

# ADR 0003 - News via RSS

**Status:** Accepted · **Date:** 2026-07-11

## Context
We want market headlines plus per-holding news, on a free tier, keyless.

## Options
| Option | Key? | Free tier | Notes |
|---|---|---|---|
| **RSS feeds + Google News RSS** | No | Effectively unlimited | Feeds in `settings.json`; per-symbol via Google News search RSS |
| NewsAPI.org | Yes | ~100 req/day, **dev / non-commercial only** | Rejected: quota + licence |
| Marketaux / GNews | Yes | ~100 req/day | Rejected: quota, keys |

## Decision
`NEWS_PROVIDER=rss` (default). Market headlines come from the RSS feeds listed in
`config/settings.json` (Moneycontrol, ET Markets, Mint, plus US feeds from WSJ
and CNBC). Per-holding news uses Google News' keyless RSS search per company name.

Each feed is fetched independently and a dead feed is skipped, so one broken
source never empties the whole news section (principle 13). Verified live
(2026-07-11): 8 market headlines and per-symbol items returned for the sample
holdings.

## Consequences
- Zero keys, no quota - fully within free-by-design.
- Feed quality varies; feeds are config, not code, so they are easy to curate.
- To swap in a news API later, add an adapter implementing `NewsProvider` and set
  `NEWS_PROVIDER` - no pipeline changes.

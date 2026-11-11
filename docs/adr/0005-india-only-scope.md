# ADR 0005 - Narrow the tracker to Indian equities only

**Status:** Accepted · **Date:** 2026-11-11

## Context
The tracker was built to hold Indian (NSE/BSE) and foreign equities side by side
in one base currency. In practice the book is entirely NSE/BSE, and the
multi-market surface was costing more than it returned:

- a currency switch whose two positions rendered identically,
- an allocation bar permanently pinned at 100% / 0%,
- a `market` column in the add-transaction form with one real answer,
- a daily FX fetch (spot + historical series) whose results nothing consumed,
- docs and ADRs describing a dual-market product that no longer matched the app.

## Decision
**The product is India-only.** One market (NSE/BSE), one currency (INR).

No market other than India is named anywhere a user can see it: the UI, the
newspaper report, the README, `docs/`, the CLI help, `config/`, or the generated
`data/*.json`.

**The engine keeps its currency abstraction.** `core/compute.py`,
`core/interfaces.py` and the price adapters still carry a `market` field and a
per-currency figures map, and `scripts/tests/test_compute.py` still exercises the
multi-currency math. This code is dormant, not wrong: `display_currencies_for()`
derives the currency list from the holdings present, so with an all-IN ledger it
returns `["INR"]`, `build_fx_rate_on()` returns `None`, and no FX call is made.
The cost of keeping it is zero at runtime; the cost of removing it would be a
rewrite of the money math and the tests that guard it.

### Rejected alternative: strip the abstraction too
Hard-coding INR through `compute.py`, `interfaces.py` and the three price
adapters would delete ~300 lines, including the 44 lines of test coverage that
currently prove average-cost accounting and realized P&L are correct. That trades
tested, inert code for untested, simpler code, and turns any future foreign
holding from a CSV edit into a refactor. Not worth it.

## News: foreign wires stay, as context
`config/settings.json` keeps two feed groups, merged into one headline list:

- `market` - Indian market wires (Moneycontrol, ET Markets, Mint).
- `global` - world macro wires (WSJ Markets, CNBC).

The second group is retained deliberately. Rate decisions, oil, and currency
moves drive the NSE tape, so those headlines are *about* the Indian book even
when they are not published in India. They are presented as plain market
headlines, with no country framing in the UI. Per-holding news was already
India-localised (`hl=en-IN&gl=IN&ceid=IN:en` in `providers/news_rss.py`) and is
unchanged.

## Consequences
- **One fewer network dependency per build.** No spot FX call and no historical
  FX series, which removes a whole class of build failure.
- **`FX_PROVIDER` and `PRICE_PROVIDER_US` are no longer documented.** The
  registry still resolves them; nothing sets them.
- **ADR 0002 and ADR 0004 are superseded** by this one. They remain in place as
  the record of why the provider and FX abstractions look the way they do.
- **The allocation widget now shows concentration** - largest position versus the
  rest - which is the allocation question that still has an answer.
- **`bhavcopy` becomes a viable sole price provider.** It rejects non-Indian
  symbols, which previously disqualified it from covering the whole book; with an
  all-IN ledger, `PRICE_PROVIDER_IN=bhavcopy` moves prices to an official NSE
  source. Not made the default here - that is a separate decision.

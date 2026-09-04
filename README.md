# Portfolio Tracker

An end-of-day (EOD) portfolio tracker for **Indian (NSE/BSE) and US equities** in
a single view. It shows total value, day change, total P&L, invested cost, a hero
value-vs-cost chart, a per-holding ledger (with trend sparklines and allocation),
and market + per-holding news.

It rebuilds itself **once a day** using **only free, open, keyless** tools and
deploys **free** on GitHub Pages. There is **no backend, no database, and no paid
API**: a scheduled job fetches data once, writes three static JSON files, and the
browser just reads those files.

Prices are delayed, end-of-day, and for personal tracking only - **not investment
advice.**

---

## What this is (and how it fits together)

```
config/holdings.csv    ─┐
                        │    GitHub Action (daily cron)
config/settings.json   ─┼─▶   scripts/fetch.py   ──▶  data/*.json  ──▶  GitHub Pages
                        │     (prices + FX + news,       (committed        (static site
providers/ (adapters)  ─┘      computes P&L)              back to repo)      reads JSON)
```

- **`scripts/fetch.py`** is the whole pipeline. It reads your config, fetches
  prices / FX / news through pluggable adapters, computes every figure, and
  writes `data/portfolio.json`, `data/history.json`, `data/news.json`.
- **`scripts/core/`** holds the pure math (`compute.py`), the fixed provider
  interfaces (`interfaces.py`), and the provider registry (`registry.py`).
- **`scripts/providers/`** holds one adapter per data source, each behind a fixed
  interface so a source is swapped by changing an env var, not code.
- **`site/`** is a plain HTML/CSS/JS frontend (no framework) that reads the JSON.
- **`data/`** is the "database": git history *is* the store. `history.json` gets
  one point appended per day and committed by CI.

Design rationale and rejected alternatives for every choice live in `docs/adr/`.

### Project layout
```
config/     holdings.csv + settings.json     (what you edit)
scripts/    fetch.py, add_lot.py, core/ (math, CSV I/O, registry), providers/, tests/
site/       index.html, styles.css, app.js    (the static frontend)
bin/        start.sh, stop.sh, restart.sh     (run it locally)
data/       generated JSON (committed by CI; the "database" is git history)
docs/adr/   architecture decisions + rejected alternatives
.github/    the daily build-and-deploy workflow
```

---

## Build and run locally

You need **Python 3.10+**. Node is **not** required. Everything below runs with no
accounts and no keys.

### 1. (Recommended) create a virtual environment
```bash
cd portfolio-tracker
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```
*What this did:* isolated the project's Python packages from your system Python.

### 2. Install dependencies
```bash
pip install -r scripts/requirements.txt
```
*What this did:* installed the three pinned fetch libraries (see
[External dependencies](#external-dependencies) below). You should see a line
ending in `Successfully installed ... yfinance-1.5.1 ...`.

> You can skip this step entirely if you only want the offline mock in step 3 -
> `--mock` uses zero third-party packages.

### 3. Build the data
Offline mock (deterministic, no network, no keys - great for a first look):
```bash
python scripts/fetch.py --mock
```
Or live end-of-day data (needs step 2; still free and keyless):
```bash
python scripts/fetch.py
```
*What this did:* wrote `data/portfolio.json`, `data/history.json`,
`data/news.json`. You should see a summary line ending in
`wrote portfolio.json, history.json, news.json`. With live data, any symbol that
fails to fetch becomes a "stale" row and the build still completes.

### 4. Assemble and preview the site
```bash
bash scripts/build_site.sh
cd public && python -m http.server 8000
```
*What this did:* copied `site/*` + `data/*` into `public/` and served it. Open
**http://localhost:8000**. Press `Ctrl+C` to stop.

> Open the site via `http://localhost:8000`, **not** by double-clicking
> `index.html` - browsers block `fetch()` on `file://`.

### 5. (Optional) run the math tests
```bash
python scripts/tests/test_compute.py
```
*What this did:* ran the pure-math unit tests (totals, FX conversion, stale
fallback, chart crossing case, lot-based avg cost, forex-aware cost, buy/sell
realized P&L, and CSV ledger parsing) with no network. You should see
`14 tests passed.`

### Manage your holdings (CSV)

Your portfolio is a **transaction ledger in `config/holdings.csv`** - one row per
buy or sale. It is plain CSV so you can edit it in a spreadsheet (Excel, Google
Sheets, Numbers) or any text editor, no brackets to break:

```csv
symbol,name,market,date,action,quantity,price
RELIANCE,Reliance Industries,IN,,,15,2680.00
AAPL,Apple,US,2024-08-01,buy,5,170.00
AAPL,Apple,US,2025-03-03,buy,7,184.00
NVDA,NVIDIA,US,2024-09-10,buy,12,88.00
NVDA,NVIDIA,US,2026-01-15,sell,4,135.00
```

- **One row per transaction.** Repeat the ticker for each further buy/sale.
- `symbol` - plain ticker (`AAPL`, `RELIANCE`); the `.NS` suffix for NSE is added in code.
- `market` - `IN` (NSE/BSE, INR) or `US` (USD).
- `date` - `YYYY-MM-DD`. Leave it (and `action`) **blank** for an opening
  position you don't want to date (valued at today's FX).
- `action` - `buy` or `sell` (blank = buy).
- `quantity` / `price` - per share, in the holding's **own** currency.

The pipeline does the rest: it replays the rows in date order with **average-cost
accounting** (sums quantity, computes the weighted-average cost, books **realized
P&L** on sells), and values each lot at the **USD/INR rate on its own date**, so
your INR/USD P&L captures currency moves as well as price moves. Historical FX is
fetched automatically (keyless) - you never enter an exchange rate.

**Working with the ledger in the app.** The masthead has three CSV controls:
- **Export CSV** - download the current `config/holdings.csv` in one click.
- **Import CSV** - pick a `.csv` file; it validates every row in the browser
  (flagging bad numbers, unknown markets, etc.) and hands back a cleaned file.
- **+ Add transaction** - a form for a single buy/sale.

> **Important:** the site is **static**, so none of these write to your repo or
> recompute in the browser. A change is only *staged* - the app shows a **"pending
> change not applied yet"** banner, flags the affected rows **pending**, and its
> transaction popup (the **⋮** button) shows the staged buy/sale with a recomputed
> net balance. Staged transactions **accumulate** for the session and **Export CSV
> includes them**, so you can make several edits and download the full result once.
> The main table's value/P&L still show the last *built* figures until you save the
> file over `config/holdings.csv` and rebuild (and commit + push for the live site) -
> because the accurate purchase-date FX, average cost, and realized P&L are computed
> by the pipeline, not the browser.

**Three ways to record a transaction:**
1. **In the app** - **+ Add transaction** (or **Import CSV**), then save the file it gives you.
2. **CLI (one command)** - edits the CSV *and* rebuilds in one go:
   ```bash
   python scripts/add_lot.py NVDA US sell 2026-03-20 10 150 --rebuild
   ```
   It writes `config/holdings.csv`, runs `fetch.py` + `build_site.sh`, then prints the
   `git commit && git push` to publish. (Drop `--rebuild` to only edit the file.)
3. **Edit `config/holdings.csv`** directly in a spreadsheet/editor, then rebuild
   (`bin/restart.sh`, or `python scripts/fetch.py && bash scripts/build_site.sh`).

**Publishing is automated - no token needed.** Once you push a change to
`config/`, the GitHub Action recomputes everything and redeploys Pages using
GitHub's built-in `GITHUB_TOKEN`. You only run `git push`; CI does the rest. (A
personal access token would only be needed if you wanted the browser itself to
commit to GitHub - a possible future option, kept out of scope for now because a
write token must never live in a public page. See `docs/ROADMAP.md`.)

**Per-holding history.** Click the **⋮** button on any row to open its full
buy/sell ledger - every transaction with a running balance, and a net-balance
summary (net quantity, average cost, invested, market value, unrealized and
realized P&L) in the holding's own currency.

**Newspaper report.** The **📰 Newspaper** button (top right) opens a printable,
newspaper-styled report: a masthead and lead story, a dual-currency **By the
Numbers** box and two mini charts (INR + USD), a 3-column **Company Briefs** grid
that pairs each holding's figures with its own headlines, and a **Market Wire**.
The **Download PDF** button prints it via the browser's Save-as-PDF.

> Column headers are case-insensitive and accept friendly aliases (`ticker`,
> `qty`, `shares`, `cost`...). A `config/holdings.json` file (lot- or legacy
> `{quantity, avg_cost}` style) is still read as a fallback if no CSV exists.
> If the FX source can't supply history for a date, that lot falls back to
> today's rate and the build still completes.

Base currency, history length, and news feeds live in **`config/settings.json`**.

---

## External dependencies

Everything the app depends on is **free and open**. There are two kinds:
Python packages (installed via pip) and external data services (called over the
network at build time only - never from the browser).

### Python packages (`scripts/requirements.txt`, pinned)

| Package | Version | Used by | What it does |
|---|---|---|---|
| **yfinance** | `1.5.1` | `providers/price_yfinance.py`, `providers/fx.py` | Reads Yahoo Finance's public endpoints for EOD closes + short history (US as-is, Indian tickers with a `.NS` suffix) and for the FX pair (`USDINR=X`). The default price and FX source. |
| **feedparser** | `6.0.12` | `providers/news_rss.py` | Parses RSS/Atom feeds into structured entries, for both the market headlines and the per-holding Google News search results. |
| **jugaad-data** | `0.33.1` | `providers/price_bhavcopy.py` | Optional official NSE end-of-day (bhavcopy) source for Indian equities. Absorbs NSE's URL/cookie churn so we don't hand-roll scraping. Only imported when `PRICE_PROVIDER_IN=bhavcopy`. |

Notes:
- **Lazy imports.** Each heavy package is imported *inside* the adapter method
  that needs it, so `python scripts/fetch.py --mock` runs with none of them
  installed.
- **Transitive deps** (installed automatically by pip): `yfinance` pulls in
  `pandas`, `numpy`, `requests`, `curl_cffi`, `beautifulsoup4`; `jugaad-data`
  pulls in `appdirs`, `click`, `requests`. `feedparser` pulls in `sgmllib3k`.
- **The Twelve Data adapter uses no package** - it calls the API with the Python
  standard library (`urllib`) only.
- **jugaad-data workaround:** version `0.33.1` creates its on-disk cache with a
  non-idempotent `os.makedirs` guarded by a check-then-create race, which throws
  `[Errno 17] File exists` when several symbols are fetched in a loop. The
  bhavcopy adapter pre-creates that cache directory with `exist_ok=True` so the
  library never hits its racy branch (see `providers/price_bhavcopy.py` and
  ADR-0002).

### External data services (called at build time, keyless by default)

| Service | Used by | Purpose | Key? | Free tier |
|---|---|---|---|---|
| **Yahoo Finance** (via yfinance) | `price_yfinance`, `fx` | Default EOD prices (IN + US) and the FX rate | No | No formal limit (unofficial) |
| **NSE bhavcopy** (via jugaad-data) | `price_bhavcopy` | Optional official Indian EOD prices | No | Unlimited, official |
| **Google News RSS** | `news_rss` | Per-holding company news (search RSS per name) | No | Effectively unlimited |
| **Publisher RSS feeds** (Moneycontrol, ET Markets, Mint, WSJ, CNBC) | `news_rss` | Market headlines; the feed list is in `settings.json` | No | Effectively unlimited |
| **open.er-api.com** | `fx` (`exchangerate_host`) | Keyless FX fallback behind the same interface | No | Open API, no key |
| **Twelve Data** | `price_twelvedata` | Optional keyed US/IN price fallback for reliability | **Yes** | 800 req/day, 8 req/min |

The **only** secret in the entire system is the optional `TWELVEDATA_API_KEY`,
and it is used at build time only (in CI secrets) - it never reaches the browser.

### Swapping a provider (config, not code)
Each concern is selected by an env var; defaults are the most liberal keyless
option. The three places always agree: **env** selects, **code** implements the
adapter, **docs/adr** records why.

| Env var | Default | Alternatives |
|---|---|---|
| `PRICE_PROVIDER_IN` | `yfinance` | `bhavcopy`, `twelvedata` |
| `PRICE_PROVIDER_US` | `yfinance` | `twelvedata` |
| `NEWS_PROVIDER` | `rss` | - |
| `FX_PROVIDER` | `yfinance` | `exchangerate_host` |

Example - use official NSE data for Indian holdings:
```bash
PRICE_PROVIDER_IN=bhavcopy python scripts/fetch.py
```
For local runs, copy `.env.example` to `.env` and edit it. In CI, set repo
**Settings -> Variables** (and a Secret only if you pick `twelvedata`).

---

## Frontend dependencies

The site itself has **no build step and no JS framework**. It is one HTML file,
one CSS file, and one vanilla-JS file that fetch the three JSON files and render.
The only external asset is **Google Fonts** (Space Grotesk, Inter, JetBrains
Mono), loaded via a stylesheet link; if it is blocked, the page falls back to
system fonts and still works.

---

## Deploy free on GitHub Pages

The included GitHub Action (`.github/workflows/update.yml`) runs `fetch.py` on a
daily cron (after US close) and on config/site/script changes, commits refreshed
`data/*.json` back to the repo, and publishes `public/` to GitHub Pages -
keyless unless you opt into Twelve Data.

Full copy-paste setup steps (create repo, push, enable Pages, run the workflow),
each with a plain-language "what this did", are in
[`docs/DEPLOY.md`](docs/DEPLOY.md).

## Currency views

A global toggle (top right of the page) shows the whole portfolio in one of:
- **Native** - each holding row in its own currency (INR for IN, USD for US). The
  summary has no single currency, so it shows **both** (dual INR + USD figures)
  and **two charts**, one per currency.
- **INR** - every number (including per-share Avg cost / Last) in the base currency.
- **USD** - every number in US dollars.

The pipeline precomputes every figure in each view (cost basis is forex-aware, so
INR/USD P&L includes currency moves as well as price moves; a **Realized** figure
appears once you've sold something), so switching is instant and no FX math
happens in the browser. Your choice is remembered locally.

## Reading the hero chart (the "cost-basis waterline")

- The **solid line** is your portfolio's total value over ~180 trading days.
- The **dashed horizontal line** is your **cost basis** (what you paid). The area
  between them fills **green where value is above cost** (in profit) and **red
  where below** (at a loss); the line and the end dot take the ending colour.
- So a line that starts under the dashed line and rises through it shows the
  moment your position moved from a loss into a gain.
- In **Native** view you get **two charts** (INR and USD), since a mixed-currency
  book has no single value; **INR**/**USD** view shows one chart in that currency.

**Hover** any point on the chart for a tooltip with the date, that day's value,
the day-over-day change, and P&L versus cost.

The curve is seeded on the first build by reconstructing history from each
holding's own price history (`backfill_history`), then one real point is appended
per day. If a rebuild's total is wildly out of scale versus the last point (for
example switching mock <-> live data, or a large config change), the pipeline
**rebuilds the whole curve** instead of appending a misleading vertical spike.

## Data contract (what the frontend reads)
```
portfolio.json: { generated_at, base_currency, display_currencies:[..],
  fx:{ CCY:rate_into_base },
  totals:{ <CCY>:{ value, cost, pnl, pnl_pct, day, day_pct }, .. },  // per display CCY
  holdings:[ { symbol, name, market, currency, quantity, avg_cost, last, prev_close,
    spark:[..native closes..], weight_pct, stale, error,
    figures:{ NATIVE:{ccy,value,cost,avg,last,pnl,pnl_pct,realized,day,day_pct},
              <CCY>:{..}, .. } } ],
  config_holdings:[..] }   // raw ledger, so the app's Add-transaction builder can export CSV
    // quantity + avg_cost are computed from the CSV lots; figures are forex-aware,
    // and totals[<CCY>] additionally carry `realized` (P&L booked on sales).
history.json:  { base_currency, display_currencies:[..], generated_at,
                 series:[ { date, value:{<CCY>:n,..}, cost:{<CCY>:n,..} } ] }
news.json:     { generated_at, market:[ {title,url,source,published} ],
                 by_symbol:{ SYMBOL:[ {title,url,source,published,symbol} ] } }
```

## License
MIT - see [`LICENSE`](LICENSE).

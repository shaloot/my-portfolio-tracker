# Portfolio Tracker

An end-of-day (EOD) portfolio tracker for **Indian (NSE/BSE) equities**. Every
figure is in **INR**. It shows total value, day change, total P&L, invested cost,
a hero value-vs-cost chart, a per-holding ledger (with trend sparklines and
concentration), and market + per-holding news.

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
                        │     (prices + news,            (committed        (static site
providers/ (adapters)  ─┘      computes P&L)              back to repo)      reads JSON)
```

- **`scripts/fetch.py`** is the whole pipeline. It reads your config, fetches
  prices and news through pluggable adapters, computes every figure, and
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
*What this did:* ran the pure-math unit tests (totals, currency conversion,
stale fallback, chart crossing case, lot-based avg cost, conversion-aware cost,
buy/sell realized P&L, and CSV ledger parsing) with no network. You should see
`14 tests passed.`

### Manage your holdings (CSV)

Your portfolio is a **transaction ledger in `config/holdings.csv`** - one row per
buy or sale. It is plain CSV so you can edit it in a spreadsheet (Excel, Google
Sheets, Numbers) or any text editor, no brackets to break:

```csv
symbol,name,market,date,action,quantity,price
RELIANCE,Reliance Industries,IN,,,15,2680.00
INFY,Infosys,IN,2024-08-01,buy,40,1420.50
INFY,Infosys,IN,2025-03-03,buy,20,1655.00
TCS,TCS,IN,2024-09-10,buy,12,3880.00
TCS,TCS,IN,2026-01-15,sell,4,4135.00
```

- **One row per transaction.** Repeat the ticker for each further buy/sale.
- `symbol` - plain ticker (`RELIANCE`, `INFY`); the `.NS` suffix for NSE is added in code.
- `market` - always `IN` (NSE/BSE). The column is kept so existing ledgers and
  spreadsheet exports import unchanged; a blank cell is read as `IN`.
- `date` - `YYYY-MM-DD`. Leave it (and `action`) **blank** for an opening
  position you don't want to date.
- `action` - `buy` or `sell` (blank = buy).
- `quantity` / `price` - per share, in INR.

The pipeline does the rest: it replays the rows in date order with **average-cost
accounting** - summing quantity, computing the weighted-average cost, and booking
**realized P&L** on sells.

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
> because the accurate average cost and realized P&L are computed
> by the pipeline, not the browser.

**Three ways to record a transaction:**
1. **In the app** - **+ Add transaction** (or **Import CSV**), then save the file it gives you.
2. **CLI (one command)** - edits the CSV *and* rebuilds in one go:
   ```bash
   python scripts/add_lot.py TCS sell 2026-03-20 10 4150 --rebuild
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
newspaper-styled report: a masthead and lead story, a **By the Numbers** box
and a value-vs-cost chart, a 3-column **Company Briefs** grid
that pairs each holding's figures with its own headlines, and a **Market Wire**.
The **Download PDF** button prints it via the browser's Save-as-PDF.

> Column headers are case-insensitive and accept friendly aliases (`ticker`,
> `qty`, `shares`, `cost`...). A `config/holdings.json` file (lot- or legacy
> `{quantity, avg_cost}` style) is still read as a fallback if no CSV exists.

Base currency, history length, and news feeds live in **`config/settings.json`**.

---

## External dependencies

Everything the app depends on is **free and open**. There are two kinds:
Python packages (installed via pip) and external data services (called over the
network at build time only - never from the browser).

### Python packages (`scripts/requirements.txt`, pinned)

| Package | Version | Used by | What it does |
|---|---|---|---|
| **yfinance** | `1.5.1` | `providers/price_yfinance.py` | Reads Yahoo Finance's public endpoints for EOD closes + short history (Indian tickers get a `.NS` suffix). The default price source. |
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
| **Yahoo Finance** (via yfinance) | `price_yfinance` | Default EOD prices for NSE/BSE tickers | No | No formal limit (unofficial) |
| **NSE bhavcopy** (via jugaad-data) | `price_bhavcopy` | Optional official Indian EOD prices | No | Unlimited, official |
| **Google News RSS** | `news_rss` | Per-holding company news (search RSS per name) | No | Effectively unlimited |
| **Publisher RSS feeds** | `news_rss` | Market headlines - Indian wires plus world-macro wires; the feed list is in `settings.json` | No | Effectively unlimited |
| **Twelve Data** | `price_twelvedata` | Optional keyed NSE price fallback for reliability | **Yes** | 800 req/day, 8 req/min |

The **only** secret in the entire system is the optional `TWELVEDATA_API_KEY`,
and it is used at build time only (in CI secrets) - it never reaches the browser.

### Swapping a provider (config, not code)
Each concern is selected by an env var; defaults are the most liberal keyless
option. The three places always agree: **env** selects, **code** implements the
adapter, **docs/adr** records why.

| Env var | Default | Alternatives |
|---|---|---|
| `PRICE_PROVIDER_IN` | `yfinance` | `bhavcopy`, `twelvedata` |
| `NEWS_PROVIDER` | `rss` | - |

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
daily cron (after the NSE close) and on config/site/script changes, commits refreshed
`data/*.json` back to the repo, and publishes `public/` to GitHub Pages -
keyless unless you opt into Twelve Data.

Full copy-paste setup steps (create repo, push, enable Pages, run the workflow),
each with a plain-language "what this did", are in
[`docs/DEPLOY.md`](docs/DEPLOY.md).

## Reading the hero chart (the "cost-basis waterline")

- The **solid line** is your portfolio's total value over ~180 trading days.
- The **dashed horizontal line** is your **cost basis** (what you paid). The area
  between them fills **green where value is above cost** (in profit) and **red
  where below** (at a loss); the line and the end dot take the ending colour.
- So a line that starts under the dashed line and rises through it shows the
  moment your position moved from a loss into a gain.

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
    // quantity + avg_cost are computed from the CSV lots, and totals[<CCY>]
    // additionally carry `realized` (P&L booked on sales).
history.json:  { base_currency, display_currencies:[..], generated_at,
                 series:[ { date, value:{<CCY>:n,..}, cost:{<CCY>:n,..} } ] }
news.json:     { generated_at, market:[ {title,url,source,published} ],
                 by_symbol:{ SYMBOL:[ {title,url,source,published,symbol} ] } }
```

## License
MIT - see [`LICENSE`](LICENSE).

#!/usr/bin/env python3
"""Build-time data pipeline.

Reads config/, fetches EOD prices + FX + news through the selected adapters,
computes the portfolio, and writes the three JSON files the static site reads.
Runs in CI on a daily cron; run locally with --mock to preview with no network.

Usage:
    python fetch.py                 # use configured/default providers (live)
    python fetch.py --mock          # deterministic offline data (no keys/network)
    python fetch.py --out ../data   # override the output directory
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))          # make `core` and `providers` importable

from core import compute  # noqa: E402


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def build_fx_rate_on(fx_provider, base_ccy: str, holdings: list, quotes: dict,
                     fx_name: str):
    """Build a (currency, date) -> rate-into-base lookup from historical FX.

    Used to (a) value each purchase lot at the FX rate on its own date and
    (b) reconstruct the multi-currency history curve. Fetches from the earliest
    date we care about (earliest lot or earliest price-history point) through
    today. Returns None if there is no non-base currency, or if no history is
    available (callers then fall back to today's rate).
    """
    from datetime import date, timedelta

    # Non-base currencies actually held.
    ccys = {("INR" if h.get("market") == "IN" else "USD") for h in holdings}
    ccys.discard(base_ccy)
    if not ccys:
        return None

    # Earliest date we need a rate for: oldest lot, or oldest price-history point.
    dates: list[str] = []
    for h in holdings:
        for lt in (h.get("lots") or []):
            if lt.get("date"):
                dates.append(str(lt["date"])[:10])
    for q in quotes.values():
        if q.ok and q.history:
            dates.append(str(q.history[0]["date"])[:10])
    start = min(dates) if dates else (date.today() - timedelta(days=400)).isoformat()
    try:  # pad back so a rate exists on/before the earliest date
        start = (date.fromisoformat(start[:10]) - timedelta(days=10)).isoformat()
    except ValueError:
        pass

    series: dict[str, list] = {}
    for ccy in sorted(ccys):
        try:
            pts = fx_provider.get_rate_series(ccy, base_ccy, start)
        except Exception as e:
            print(f"  ! fx history {ccy}->{base_ccy} failed ({e}); "
                  f"cost/curve use today's rate", file=sys.stderr)
            pts = {}
        if pts:
            series[ccy] = sorted(pts.items())
            print(f"[fx] {fx_name}: {len(pts)} historical {ccy}->{base_ccy} points "
                  f"from {start}")
    if not series:
        return None

    def rate_on(ccy: str, d: str):
        arr = series.get(ccy)
        if not arr:
            return None
        d = str(d)[:10]
        best = None                       # nearest rate on or before date d
        for date_iso, rate in arr:
            if date_iso <= d:
                best = rate
            else:
                break
        return best

    return rate_on


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true",
                    help="use deterministic offline adapters (no network/keys)")
    ap.add_argument("--config", default=str(HERE.parent / "config"))
    ap.add_argument("--out", default=str(HERE.parent / "data"))
    args = ap.parse_args()

    if args.mock:
        os.environ.update({
            "PRICE_PROVIDER_IN": "mock", "PRICE_PROVIDER_US": "mock",
            "NEWS_PROVIDER": "mock", "FX_PROVIDER": "mock",
        })

    # Register mock adapters only when needed (keeps the import graph light).
    from core import registry
    if args.mock:
        from providers.mock import MockPrices, MockNews, MockFx
        registry.PRICE_ADAPTERS["mock"] = MockPrices
        registry.NEWS_ADAPTERS["mock"] = MockNews
        registry.FX_ADAPTERS["mock"] = MockFx

    cfg_dir = Path(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = load_json(cfg_dir / "settings.json", {}) or {}
    from core import holdings_io
    holdings, src = holdings_io.read_holdings(cfg_dir)
    if not holdings:
        print("No holdings found in config/holdings.csv (or holdings.json)", file=sys.stderr)
        return 1
    print(f"[config] {len(holdings)} holdings from {src}")

    base_ccy = settings.get("base_currency", "INR")
    history_days = int(settings.get("history_days", 180))

    # ---- prices, grouped by market so each market uses its own adapter -------
    quotes: dict = {}
    by_market: dict[str, list] = {}
    for h in holdings:
        by_market.setdefault(h["market"], []).append(h)

    for market, hs in by_market.items():
        name, provider = registry.price_provider_for(market)
        print(f"[prices] {market}: {name} ({len(hs)} symbols)")
        for q in provider.get_quotes(hs, history_days):
            quotes[q.symbol] = q
            flag = "ok" if q.ok else f"STALE ({q.error})"
            print(f"    {q.symbol:<12} {flag}", file=sys.stderr if not q.ok else sys.stdout)

    # ---- fx: one rate per non-base currency actually present ----------------
    fx_name, fx = registry.fx_provider()
    currencies = {q.currency for q in quotes.values()} | {base_ccy}
    fx_map = {base_ccy: 1.0}
    for ccy in sorted(currencies):
        if ccy == base_ccy:
            continue
        try:
            fx_map[ccy] = fx.get_rate(ccy, base_ccy)
            print(f"[fx] {fx_name}: 1 {ccy} = {fx_map[ccy]:.4f} {base_ccy}")
        except Exception as e:
            fx_map[ccy] = 1.0
            print(f"  ! fx {ccy}->{base_ccy} failed ({e}); falling back to 1.0",
                  file=sys.stderr)

    # ---- historical FX for lot-dated cost basis + multi-currency views ------
    # Value each lot at the FX rate on its own date so base/USD cost (and P&L)
    # capture currency moves, and reconstruct the history curve in each currency.
    fx_rate_on = build_fx_rate_on(fx, base_ccy, holdings, quotes, fx_name)
    displays = compute.display_currencies_for(holdings, base_ccy)
    print(f"[views] currencies: {', '.join(displays)} (+ NATIVE)")

    # ---- compute portfolio + rolling history --------------------------------
    portfolio = compute.build_portfolio(holdings, quotes, base_ccy, fx_map,
                                        fx_rate_on, displays)
    prev_history = load_json(out_dir / "history.json", {}) or {}

    def _last_base_value(hist: dict):
        s = (hist or {}).get("series") or []
        if not s:
            return None
        v = s[-1].get("value")
        if isinstance(v, dict):
            return v.get(base_ccy)
        return s[-1].get("value_base")  # tolerate the old single-currency shape

    # Rebuild the whole curve on first run, on a schema change, or when today's
    # total is wildly out of scale vs the last point (e.g. switching mock<->live,
    # or a big config change) - appending there would draw a false vertical spike.
    last_val = _last_base_value(prev_history)
    today_val = portfolio["totals"][base_ccy]["value"]
    jumped = bool(last_val) and abs(today_val - last_val) > max(last_val, 1.0)  # >100%
    if len(prev_history.get("series", [])) < 2 or "display_currencies" not in prev_history or jumped:
        if jumped:
            print(f"[history] today's total ({today_val:,.0f}) is far from the last "
                  f"point ({last_val:,.0f}); rebuilding the curve", file=sys.stderr)
        history = compute.backfill_history(holdings, quotes, base_ccy, fx_map,
                                           history_days, fx_rate_on, displays)
        history = compute.build_history(history, portfolio, history_days)
    else:
        history = compute.build_history(prev_history, portfolio, history_days)

    # ---- news (any failure is isolated per feed / per symbol) ---------------
    news_name, news = registry.news_provider()
    feeds = settings.get("news_feeds", {})
    market_feeds = feeds.get("market", []) + feeds.get("us_market", [])
    try:
        market_items = news.get_market_news(
            market_feeds, int(settings.get("news_market_headlines", 8)))
    except Exception as e:
        print(f"  ! market news failed ({e})", file=sys.stderr)
        market_items = []
    per_symbol: dict = {}
    for h in holdings:
        try:
            items = news.get_symbol_news(h["symbol"], h.get("name", h["symbol"]),
                                         int(settings.get("news_per_holding", 3)))
            per_symbol[h["symbol"]] = [it.__dict__ for it in items]
        except Exception as e:
            print(f"  ! news {h['symbol']}: {e}", file=sys.stderr)
            per_symbol[h["symbol"]] = []
    print(f"[news] {news_name}: {len(market_items)} market headlines")

    news_out = {
        "generated_at": portfolio["generated_at"],
        "market": [it.__dict__ for it in market_items],
        "by_symbol": per_symbol,
    }

    # Echo the raw holdings config so the frontend's "Add transaction" builder
    # can append a lot and export an updated config/holdings.csv (it can't fetch
    # FX in the browser, so the accurate recompute happens on the next build).
    portfolio["config_holdings"] = holdings

    # ---- write --------------------------------------------------------------
    (out_dir / "portfolio.json").write_text(json.dumps(portfolio, indent=2))
    (out_dir / "history.json").write_text(json.dumps(history, indent=2))
    (out_dir / "news.json").write_text(json.dumps(news_out, indent=2))

    t = portfolio["totals"][base_ccy]
    stale = sum(1 for r in portfolio["holdings"] if r["stale"])
    print(f"\n[ok] {len(holdings)} holdings"
          + (f" ({stale} stale)" if stale else "")
          + f" | value {t['value']:,.0f} {base_ccy}"
          f" | P&L {t['pnl']:,.0f} ({t['pnl_pct']:+.2f}%)"
          f" | day {t['day']:,.0f} ({t['day_pct']:+.2f}%)")
    print(f"[ok] wrote portfolio.json, history.json, news.json -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

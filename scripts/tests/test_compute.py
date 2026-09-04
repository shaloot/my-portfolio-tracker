"""Unit tests for the pure portfolio math.

Run from the repo root with either:
    python -m pytest scripts/tests            # if pytest is installed
    python scripts/tests/test_compute.py      # plain stdlib fallback (no deps)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `core` importable

from core import compute, holdings_io
from core.interfaces import Quote


def _q(sym, market, close, prev, ccy, hist=None):
    return Quote(symbol=sym, market=market, close=close, prev_close=prev,
                 currency=ccy, history=hist or [])


def test_basic_totals_and_fx():
    holdings = [
        {"symbol": "AAA", "name": "A", "market": "IN", "quantity": 10, "avg_cost": 100.0},
        {"symbol": "BBB", "name": "B", "market": "US", "quantity": 2, "avg_cost": 50.0},
    ]
    quotes = {
        "AAA": _q("AAA", "IN", 110.0, 105.0, "INR"),
        "BBB": _q("BBB", "US", 60.0, 60.0, "USD"),
    }
    fx = {"INR": 1.0, "USD": 80.0}
    p = compute.build_portfolio(holdings, quotes, "INR", fx)

    assert p["display_currencies"] == ["INR", "USD"]
    # INR totals: AAA 10*110*1 = 1100 ; BBB 2*60*80 = 9600 ; total 10700
    assert p["totals"]["INR"]["value"] == 10700.0
    assert p["totals"]["INR"]["cost"] == 9000.0     # 10*100 + 2*50*80
    assert p["totals"]["INR"]["pnl"] == 1700.0
    # USD totals: AAA 1100/80 = 13.75 ; BBB 120 ; total 133.75
    assert p["totals"]["USD"]["value"] == 133.75
    # weights sum to ~100, largest first
    assert abs(sum(r["weight_pct"] for r in p["holdings"]) - 100.0) < 0.2
    assert p["holdings"][0]["symbol"] == "BBB"


def test_native_view_per_row():
    holdings = [{"symbol": "BBB", "name": "B", "market": "US",
                 "quantity": 2, "avg_cost": 50.0}]
    quotes = {"BBB": _q("BBB", "US", 60.0, 60.0, "USD")}
    p = compute.build_portfolio(holdings, quotes, "INR", {"INR": 1.0, "USD": 80.0})
    fig = p["holdings"][0]["figures"]
    assert fig["NATIVE"]["ccy"] == "USD"
    assert fig["NATIVE"]["value"] == 120.0            # 2*60 in USD
    assert fig["NATIVE"]["cost"] == 100.0             # 2*50 in USD, no FX
    assert fig["INR"]["value"] == 9600.0              # 2*60*80
    assert fig["USD"]["value"] == 120.0


def test_bad_ticker_is_stale_not_crash():
    holdings = [{"symbol": "ZZZ", "name": "Z", "market": "US",
                 "quantity": 5, "avg_cost": 20.0}]
    quotes = {"ZZZ": Quote(symbol="ZZZ", market="US", close=0, prev_close=0,
                           currency="USD", ok=False, error="no rows returned")}
    p = compute.build_portfolio(holdings, quotes, "INR", {"INR": 1.0, "USD": 80.0})
    row = p["holdings"][0]
    assert row["stale"] is True
    assert row["error"] == "no rows returned"
    assert row["figures"]["NATIVE"]["pnl"] == 0.0     # valued at cost => zero P&L
    assert row["figures"]["NATIVE"]["day_pct"] == 0.0
    assert row["last"] == 20.0


def test_missing_quote_entirely():
    holdings = [{"symbol": "NOPE", "name": "N", "market": "IN",
                 "quantity": 1, "avg_cost": 500.0}]
    p = compute.build_portfolio(holdings, {}, "INR", {"INR": 1.0})
    assert p["holdings"][0]["stale"] is True
    assert p["totals"]["INR"]["value"] == 500.0


def test_lot_based_native_avg_cost():
    """Multiple lots -> summed quantity and weighted-average avg_cost."""
    holdings = [{"symbol": "AAA", "name": "A", "market": "US", "lots": [
        {"date": "2025-01-10", "quantity": 5, "price": 170.0},
        {"date": "2025-06-10", "quantity": 7, "price": 184.0},
    ]}]
    quotes = {"AAA": _q("AAA", "US", 200.0, 200.0, "USD")}
    p = compute.build_portfolio(holdings, quotes, "INR", {"INR": 1.0, "USD": 80.0})
    row = p["holdings"][0]
    assert row["quantity"] == 12
    assert row["avg_cost"] == round((5 * 170 + 7 * 184) / 12, 4)  # 178.1667


def test_lot_forex_aware_cost_uses_purchase_date_fx():
    """Cost basis values each lot at the FX rate on its own date, not today's."""
    holdings = [{"symbol": "AAA", "name": "A", "market": "US", "lots": [
        {"date": "2025-01-10", "quantity": 10, "price": 100.0},
    ]}]
    quotes = {"AAA": _q("AAA", "US", 100.0, 100.0, "USD")}   # flat price: no native P&L
    fx_today = {"INR": 1.0, "USD": 90.0}                     # USD stronger now
    rate_on = lambda ccy, d: 80.0 if ccy == "USD" else None  # rate on buy date was 80
    p = compute.build_portfolio(holdings, quotes, "INR", fx_today, fx_rate_on=rate_on)
    inr = p["holdings"][0]["figures"]["INR"]
    assert inr["cost"] == 80000.0                     # 10*100*80 (purchase-date FX)
    assert inr["value"] == 90000.0                    # 10*100*90 (today's FX)
    assert inr["pnl"] == 10000.0                      # pure forex gain, in INR
    assert p["holdings"][0]["figures"]["NATIVE"]["pnl"] == 0.0   # native still flat


def test_legacy_holding_still_works():
    """Old {quantity, avg_cost} config path is unchanged (today's FX for cost)."""
    holdings = [{"symbol": "AAA", "name": "A", "market": "US",
                 "quantity": 2, "avg_cost": 50.0}]
    quotes = {"AAA": _q("AAA", "US", 60.0, 60.0, "USD")}
    p = compute.build_portfolio(holdings, quotes, "INR", {"INR": 1.0, "USD": 80.0})
    inr = p["holdings"][0]["figures"]["INR"]
    assert inr["cost"] == 2 * 50 * 80                 # today's FX, as before
    assert inr["value"] == 2 * 60 * 80


def test_sell_reduces_qty_keeps_avg_and_books_realized():
    """Average-cost: a sale reduces quantity, leaves avg cost unchanged, and
    realizes P&L on the shares sold."""
    holdings = [{"symbol": "AAA", "name": "A", "market": "US", "lots": [
        {"date": "2025-01-01", "action": "buy",  "quantity": 10, "price": 100.0},
        {"date": "2025-02-01", "action": "buy",  "quantity": 10, "price": 200.0},  # avg -> 150
        {"date": "2025-03-01", "action": "sell", "quantity": 5,  "price": 250.0},
    ]}]
    quotes = {"AAA": _q("AAA", "US", 300.0, 300.0, "USD")}
    p = compute.build_portfolio(holdings, quotes, "INR", {"INR": 1.0, "USD": 1.0})
    row = p["holdings"][0]
    assert row["quantity"] == 15                       # 20 bought - 5 sold
    assert row["avg_cost"] == 150.0                    # unchanged by the sale
    nat = row["figures"]["NATIVE"]
    assert nat["cost"] == 15 * 150.0                   # remaining basis 2250
    assert nat["value"] == 15 * 300.0                  # 4500
    assert nat["realized"] == 5 * (250.0 - 150.0)      # 500 booked
    assert p["totals"]["USD"]["realized"] == 500.0


def test_sell_forex_realized_uses_sale_date_fx():
    """Realized P&L in INR uses the FX on the sale date vs the buy date."""
    holdings = [{"symbol": "AAA", "name": "A", "market": "US", "lots": [
        {"date": "2025-01-01", "action": "buy",  "quantity": 10, "price": 100.0},
        {"date": "2025-06-01", "action": "sell", "quantity": 10, "price": 100.0},  # flat price
    ]}]
    quotes = {"AAA": _q("AAA", "US", 100.0, 100.0, "USD")}
    fx_today = {"INR": 1.0, "USD": 90.0}
    rate_on = lambda ccy, d: (80.0 if d <= "2025-01-01" else 88.0) if ccy == "USD" else None
    p = compute.build_portfolio(holdings, quotes, "INR", fx_today, fx_rate_on=rate_on)
    # fully sold -> not in the table, but realized flows to totals
    assert p["holdings"] == []
    # bought 10*100 @80 = 80,000 ; sold 10*100 @88 = 88,000 -> +8,000 INR forex gain
    assert p["totals"]["INR"]["realized"] == 8000.0
    assert p["totals"]["USD"]["realized"] == 0.0       # flat price, no USD gain


def test_per_share_figures_in_each_currency():
    """avg/last per share are provided per view so all columns can convert."""
    holdings = [{"symbol": "BBB", "name": "B", "market": "US",
                 "quantity": 2, "avg_cost": 50.0}]
    quotes = {"BBB": _q("BBB", "US", 60.0, 60.0, "USD")}
    p = compute.build_portfolio(holdings, quotes, "INR", {"INR": 1.0, "USD": 80.0})
    fig = p["holdings"][0]["figures"]
    assert fig["NATIVE"]["avg"] == 50.0 and fig["NATIVE"]["last"] == 60.0
    assert fig["INR"]["avg"] == 50.0 * 80 and fig["INR"]["last"] == 60.0 * 80


def test_backfill_history_crossing_case():
    """History must cross the cost waterline: start below cost, end above."""
    holdings = [{"symbol": "AAA", "name": "A", "market": "IN",
                 "quantity": 1, "avg_cost": 100.0}]
    hist = [{"date": f"2026-01-0{i}", "close": c}
            for i, c in enumerate([80, 90, 100, 110, 120], start=1)]
    quotes = {"AAA": _q("AAA", "IN", 120.0, 110.0, "INR", hist)}
    h = compute.backfill_history(holdings, quotes, "INR", {"INR": 1.0}, keep_days=180)
    series = h["series"]
    assert len(series) == 5
    assert series[0]["value"]["INR"] < series[0]["cost"]["INR"]     # below waterline
    assert series[-1]["value"]["INR"] > series[-1]["cost"]["INR"]   # above waterline
    assert all(s["cost"]["INR"] == 100.0 for s in series)           # flat waterline


def test_build_history_dedups_same_day_and_migrates():
    port = compute.build_portfolio(
        [{"symbol": "AAA", "name": "A", "market": "IN", "quantity": 1, "avg_cost": 90.0}],
        {"AAA": _q("AAA", "IN", 100.0, 100.0, "INR")}, "INR", {"INR": 1.0})
    # An old single-currency series is discarded and rebuilt.
    old = {"series": [{"date": "2026-07-10", "value_base": 1, "cost_base": 1}]}
    h1 = compute.build_history(old, port, keep_days=180)
    assert len(h1["series"]) == 1
    assert isinstance(h1["series"][0]["value"], dict)
    # Same-day re-run overwrites, not appends.
    h2 = compute.build_history(h1, port, keep_days=180)
    assert len(h2["series"]) == 1


def test_csv_ledger_parsing():
    """CSV ledger -> internal holdings: grouping, lots, aliases, blanks, sells."""
    csv = (
        "Ticker,Name,Market,Date,Action,Qty,Price\n"
        "RELIANCE,Reliance,IN,,,15,2680\n"          # legacy: undated -> one buy lot
        "AAPL,Apple,US,2024-08-01,buy,5,170\n"
        "AAPL,,US,2025-03-03,BUY,7,184\n"           # name from first row; case-insensitive
        "NVDA,NVIDIA,US,2024-09-10,buy,12,88\n"
        "NVDA,NVIDIA,US,2026-01-15,sell,4,135\n"
        "_note,this row is ignored,,,,,\n"
    )
    hs = holdings_io.parse_csv(csv)
    syms = [h["symbol"] for h in hs]
    assert syms == ["RELIANCE", "AAPL", "NVDA"]     # order preserved, comment skipped
    aapl = next(h for h in hs if h["symbol"] == "AAPL")
    assert aapl["name"] == "Apple" and len(aapl["lots"]) == 2
    assert aapl["lots"][0]["date"] == "2024-08-01" and aapl["lots"][1]["action"] == "buy"
    rel = next(h for h in hs if h["symbol"] == "RELIANCE")
    assert rel["lots"][0]["date"] is None and rel["lots"][0]["action"] == "buy"
    nvda = next(h for h in hs if h["symbol"] == "NVDA")
    assert [l["action"] for l in nvda["lots"]] == ["buy", "sell"]


def test_csv_round_trip():
    """to_csv(parse_csv(x)) is stable and re-parses to the same positions."""
    csv1 = holdings_io.to_csv([
        {"symbol": "AAPL", "name": "Apple", "market": "US", "lots": [
            {"date": "2024-08-01", "action": "buy", "quantity": 5, "price": 170.0},
            {"date": "2025-03-03", "action": "buy", "quantity": 7, "price": 184.0}]},
        {"symbol": "TCS", "name": "Tata", "market": "IN",
         "quantity": 10, "avg_cost": 3800.0},   # legacy -> single row
    ])
    hs = holdings_io.parse_csv(csv1)
    assert holdings_io.to_csv(hs) == csv1
    assert len(hs) == 2 and hs[1]["lots"][0]["quantity"] == 10.0


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()

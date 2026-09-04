"""Pure portfolio math. No I/O, no network - trivial to test and reason about.

Given holdings + quotes + FX, produce exactly the JSON the site reads. Everything
the browser needs is precomputed here so the frontend stays dumb and static
(principle 4: static-first, server-never).

Multi-currency views
--------------------
The user enters each lot only in the holding's own (native) currency. This module
expresses every money figure in three views:
  - NATIVE : each holding in its own currency (INR for IN, USD for US)
  - <base> : everything in the base currency (INR)
  - USD    : everything in USD (if any USD holding is present)
Cost basis is forex-aware: each lot is converted at the FX rate on ITS OWN
purchase date, so a currency move between buying and today shows up as P&L. Value
and day-change use today's rate.

FX helpers here take:
  - `fx` (a.k.a. fx_today): {currency: multiplier into base} spot rate, base -> 1.0
  - `fx_rate_on`: optional callable (currency, date_iso) -> rate-into-base|None,
    giving the historical rate on a past date (None => fall back to today's).
Cross rates are derived as  from->to = (from->base) / (to->base).
"""
from __future__ import annotations

from datetime import datetime, timezone

from .interfaces import Quote

FIGURE_KEYS = ("value", "cost", "pnl", "pnl_pct", "day", "day_pct")


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fallback_currency(market: str) -> str:
    return "INR" if market == "IN" else "USD"


def display_currencies_for(holdings: list[dict], base_currency: str) -> list[str]:
    """Base currency first, then any other native currency actually held."""
    order = [base_currency]
    for h in holdings:
        ccy = _fallback_currency(h.get("market", "US"))
        if ccy not in order:
            order.append(ccy)
    return order


def lots_of(h: dict) -> list[dict]:
    """Normalise a holding into a list of purchase lots [{date, quantity, price}].

    New style: the holding carries `lots: [{date, quantity, price}, ...]`.
    Legacy style: `{quantity, avg_cost}` becomes a single undated lot (date=None),
    so old configs keep working - they just can't be FX-dated and fall back to
    today's rate for cost basis.
    """
    raw = h.get("lots")
    if raw:
        out = []
        for lt in raw:
            try:
                out.append({"date": lt.get("date"),
                            "action": str(lt.get("action", "buy")).lower(),
                            "quantity": abs(float(lt["quantity"])),
                            "price": float(lt["price"])})
            except (KeyError, TypeError, ValueError):
                continue  # skip a malformed lot rather than crash the build
        if out:
            return out
    return [{"date": None, "action": "buy",
             "quantity": float(h["quantity"]),
             "price": float(h["avg_cost"])}]


def _tracked_currencies(native: str, displays: list[str]) -> list[str]:
    out = [native]
    for c in displays:
        if c not in out:
            out.append(c)
    return out


def process_lots(h: dict, native: str, currencies: list[str],
                 fx_rate_on, fx_today: dict[str, float]) -> dict:
    """Replay a holding's buys and sells in date order using average-cost
    accounting, tracking cost basis + realized P&L in every currency at once.

    Buys add to quantity and cost. Sells reduce quantity, remove cost at the
    running average (so the average of the remaining shares is unchanged), and
    book realized P&L = proceeds - cost removed. Each amount is converted at the
    FX rate on that transaction's own date (forex-aware). Returns:
      { quantity, cost:{ccy:basis}, realized:{ccy:pnl}, avg_native }
    """
    lots = sorted(lots_of(h), key=lambda l: l["date"] or "")  # undated (legacy) first
    qty = 0.0
    cost = {c: 0.0 for c in currencies}
    realized = {c: 0.0 for c in currencies}

    for l in lots:
        q, price, date = l["quantity"], l["price"], l["date"]
        if l["action"] == "sell":
            if qty <= 0:
                continue                       # nothing to sell; ignore stray sale
            s = min(q, qty)                    # never sell more than held
            for c in currencies:
                avg_c = cost[c] / qty if qty else 0.0
                proceeds = convert(s * price, native, c, date, fx_rate_on, fx_today)
                realized[c] += proceeds - s * avg_c
                cost[c] -= s * avg_c
            qty -= s
        else:                                  # buy
            for c in currencies:
                cost[c] += convert(q * price, native, c, date, fx_rate_on, fx_today)
            qty += q

    return {"quantity": qty, "cost": cost, "realized": realized,
            "avg_native": (cost[native] / qty) if qty else 0.0}


def _rate_to_base(ccy: str, date: str | None, fx_rate_on, fx_today: dict[str, float]) -> float:
    """`ccy` -> base multiplier on `date` (historical if available, else today's)."""
    if date and fx_rate_on:
        r = fx_rate_on(ccy, date)
        if r:
            return r
    return fx_today.get(ccy, 1.0)


def convert(amount: float, from_ccy: str, to_ccy: str, date: str | None,
            fx_rate_on, fx_today: dict[str, float]) -> float:
    """Convert `amount` from one currency to another using rates on `date`
    (or today if `date` is None). Cross rate = (from->base) / (to->base)."""
    if from_ccy == to_ccy:
        return amount
    r_from = _rate_to_base(from_ccy, date, fx_rate_on, fx_today)
    r_to = _rate_to_base(to_ccy, date, fx_rate_on, fx_today)
    return amount * r_from / r_to if r_to else amount


def _figures(qty, native_ccy, last, prev, cost, realized,
             target, fx_rate_on, fx_today) -> dict:
    """All money figures for one holding, expressed in `target` currency.

    `cost` and `realized` are the accounting outputs (already in `target`).
    Value/day use today's FX. avg/last per share are derived so the frontend can
    show every column in the chosen currency (avg = cost/qty, last = value/qty).
    """
    value = convert(qty * last, native_ccy, target, None, fx_rate_on, fx_today)
    prev_value = convert(qty * prev, native_ccy, target, None, fx_rate_on, fx_today)
    pnl = value - cost
    day = value - prev_value
    return {
        "ccy": target,
        "value": _round(value),
        "cost": _round(cost),
        "avg": _round(cost / qty, 4) if qty else 0.0,
        "last": _round(value / qty, 4) if qty else _round(
            convert(last, native_ccy, target, None, fx_rate_on, fx_today), 4),
        "pnl": _round(pnl),
        "pnl_pct": _round(pnl / cost * 100.0 if cost else 0.0),
        "realized": _round(realized),
        "day": _round(day),
        "day_pct": _round(day / prev_value * 100.0 if prev_value else 0.0),
        "_prev": prev_value,   # internal, used for totals; stripped before output
    }


def build_portfolio(holdings: list[dict], quotes: dict[str, Quote],
                    base_currency: str, fx: dict[str, float],
                    fx_rate_on=None, display_currencies: list[str] | None = None) -> dict:
    """Compute per-holding rows + portfolio totals, in every display currency.

    Each holding gets a `figures` map: {NATIVE, <base>, USD, ...}. Totals are
    given per display currency (NATIVE totals are undefined for a mixed-currency
    book, so the frontend shows the base-currency total in NATIVE view).
    """
    displays = display_currencies or display_currencies_for(holdings, base_currency)

    rows: list[dict] = []
    tot = {c: {"value": 0.0, "cost": 0.0, "prev": 0.0, "realized": 0.0} for c in displays}

    for h in holdings:
        sym = h["symbol"]
        q = quotes.get(sym)
        live = bool(q and q.ok)
        native = q.currency if live else _fallback_currency(h["market"])
        currencies = _tracked_currencies(native, displays)

        pos = process_lots(h, native, currencies, fx_rate_on, fx)
        qty, avg = pos["quantity"], pos["avg_native"]
        if live:
            last = q.close
            prev = q.prev_close if q.prev_close else q.close
        else:
            # Graceful fallback: value the row at its own cost and flag it stale.
            last = avg
            prev = avg

        # Figures per view: NATIVE plus each display currency.
        figures = {}
        for view in ["NATIVE"] + list(displays):
            target = native if view == "NATIVE" else view
            figures[view] = _figures(qty, native, last, prev,
                                     pos["cost"][target], pos["realized"][target],
                                     target, fx_rate_on, fx)

        # Accumulate totals in each display currency.
        for c in displays:
            f = figures[c]
            tot[c]["value"] += f["value"]
            tot[c]["cost"] += f["cost"]
            tot[c]["prev"] += f["_prev"]
            tot[c]["realized"] += f["realized"]

        for f in figures.values():
            f.pop("_prev", None)

        rows.append({
            "symbol": sym,
            "name": h.get("name", sym),
            "market": h["market"],
            "currency": native,
            "quantity": _round(qty, 4),
            "avg_cost": _round(avg, 4),
            "last": _round(last, 4),
            "prev_close": _round(prev, 4),
            "spark": [_round(p["close"], 4) for p in (q.history if live else [])],
            "stale": not live,
            "error": (q.error if (q and not q.ok) else None),
            "figures": figures,
        })

    # Drop fully-closed positions from the table (their realized P&L stays in totals).
    rows = [r for r in rows if r["quantity"] > 1e-9]

    # Allocation weight is view-independent (same ratio in any currency); use base.
    total_base = tot[base_currency]["value"]
    for r in rows:
        r["weight_pct"] = _round(r["figures"][base_currency]["value"] / total_base * 100.0
                                 if total_base else 0.0)

    rows.sort(key=lambda r: r["figures"][base_currency]["value"], reverse=True)

    totals = {}
    for c in displays:
        v, cost, pv, rz = (tot[c]["value"], tot[c]["cost"], tot[c]["prev"], tot[c]["realized"])
        totals[c] = {
            "value": _round(v),
            "cost": _round(cost),
            "pnl": _round(v - cost),
            "pnl_pct": _round((v - cost) / cost * 100.0 if cost else 0.0),
            "realized": _round(rz),
            "day": _round(v - pv),
            "day_pct": _round((v - pv) / pv * 100.0 if pv else 0.0),
        }

    return {
        "generated_at": _now_iso(),
        "base_currency": base_currency,
        "display_currencies": displays,
        "fx": {k: _round(v, 6) for k, v in fx.items()},
        "totals": totals,
        "holdings": rows,
    }


def backfill_history(holdings: list[dict], quotes: dict[str, Quote],
                     base_currency: str, fx: dict[str, float], keep_days: int,
                     fx_rate_on=None, display_currencies: list[str] | None = None) -> dict:
    """Reconstruct a daily value curve (per display currency) from each holding's
    own price history, so the first deploy already shows a meaningful hero chart.

    Each date is valued at that date's FX (historical if available), which is
    consistent with the forex-aware cost basis. Cost is the flat waterline.
    """
    displays = display_currencies or display_currencies_for(holdings, base_currency)

    by_date: dict[str, dict[str, float]] = {}
    for h in holdings:
        q = quotes.get(h["symbol"])
        if not (q and q.ok):
            continue
        for pt in q.history:
            by_date.setdefault(pt["date"], {})[h["symbol"]] = pt["close"]

    def native_of(h: dict) -> str:
        q = quotes.get(h["symbol"])
        return q.currency if (q and q.ok) else _fallback_currency(h["market"])

    # Current quantity + remaining cost basis (post buys/sells), forex-aware.
    qty_of: dict[str, float] = {}
    cost_by_ccy = {c: 0.0 for c in displays}
    for h in holdings:
        native = native_of(h)
        pos = process_lots(h, native, _tracked_currencies(native, displays), fx_rate_on, fx)
        qty_of[h["symbol"]] = pos["quantity"]
        for c in displays:
            cost_by_ccy[c] += pos["cost"][c]

    series: list[dict] = []
    last_close: dict[str, float] = {}
    for d in sorted(by_date):
        val = {c: 0.0 for c in displays}
        for h in holdings:
            sym = h["symbol"]
            close = by_date[d].get(sym, last_close.get(sym))
            if close is None:
                continue
            last_close[sym] = close
            native = native_of(h)
            for c in displays:
                val[c] += convert(qty_of[sym] * close, native, c, d, fx_rate_on, fx)
        series.append({
            "date": d,
            "value": {c: _round(val[c]) for c in displays},
            "cost": {c: _round(cost_by_ccy[c]) for c in displays},
        })

    if keep_days and len(series) > keep_days:
        series = series[-keep_days:]
    return {
        "base_currency": base_currency,
        "display_currencies": displays,
        "generated_at": _now_iso(),
        "series": series,
    }


def _is_new_history(prev_history: dict) -> bool:
    """True if prev_history uses the multi-currency point shape {value:{...}}."""
    series = (prev_history or {}).get("series") or []
    return bool(series) and isinstance(series[0].get("value"), dict)


def build_history(prev_history: dict, portfolio: dict, keep_days: int) -> dict:
    """Append today's totals (per display currency) to the rolling series.
    De-dups by date, so re-running on the same day overwrites rather than piles up.
    A pre-multicurrency series is discarded and rebuilt (it can't be back-converted).
    """
    displays = portfolio["display_currencies"]
    series = list(prev_history.get("series", [])) if _is_new_history(prev_history) else []
    today = datetime.now(timezone.utc).date().isoformat()
    point = {
        "date": today,
        "value": {c: portfolio["totals"][c]["value"] for c in displays},
        "cost": {c: portfolio["totals"][c]["cost"] for c in displays},
    }
    series = [p for p in series if p.get("date") != today]
    series.append(point)
    series.sort(key=lambda p: p["date"])
    if keep_days and len(series) > keep_days:
        series = series[-keep_days:]
    return {
        "base_currency": portfolio["base_currency"],
        "display_currencies": displays,
        "generated_at": portfolio["generated_at"],
        "series": series,
    }

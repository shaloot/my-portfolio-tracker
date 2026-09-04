"""yfinance price adapter - the default, keyless source for both markets.

US tickers are used as-is; Indian tickers get an `.NS` (NSE) suffix. yfinance is
unofficial (it reads Yahoo Finance's public endpoints), so it can break without
notice - which is exactly why bhavcopy and twelvedata sit behind the same
interface as drop-in swaps (see docs/adr/0002).

One bad symbol never raises: it comes back as a Quote with ok=False, which the
compute step renders as a "stale" row (principle 13).
"""
from __future__ import annotations

from core.interfaces import Quote, PriceProvider


def _yf_symbol(symbol: str, market: str) -> str:
    return f"{symbol}.NS" if market == "IN" else symbol


class YFinancePrices(PriceProvider):
    id = "yfinance"
    markets = ("IN", "US")

    def get_quotes(self, symbols, history_days):
        import yfinance as yf  # lazy: --mock needs nothing installed

        out = []
        for s in symbols:
            sym, market = s["symbol"], s["market"]
            currency = "INR" if market == "IN" else "USD"
            try:
                t = yf.Ticker(_yf_symbol(sym, market))
                df = t.history(period=f"{max(history_days, 7)}d",
                               interval="1d", auto_adjust=False)
                if df is None or df.empty:
                    raise ValueError("no price data (ticker may be delisted or renamed)")
                closes = df["Close"].dropna()
                if closes.empty:
                    raise ValueError("no closing prices (ticker may be delisted or renamed)")
                hist = [{"date": idx.date().isoformat(), "close": float(v)}
                        for idx, v in closes.items()]
                close = hist[-1]["close"]
                prev = hist[-2]["close"] if len(hist) > 1 else close
                out.append(Quote(symbol=sym, market=market, close=close,
                                 prev_close=prev, currency=currency, history=hist))
            except Exception as e:  # never let one bad symbol kill the run
                out.append(Quote(symbol=sym, market=market, close=0, prev_close=0,
                                 currency=currency, ok=False, error=str(e)[:200]))
        return out

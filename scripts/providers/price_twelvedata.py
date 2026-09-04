"""Twelve Data adapter (keyed fallback, stdlib-only - no extra package).

Free tier: 800 API credits/day, 8 requests/minute, delayed EOD; covers US, NSE,
and 50+ exchanges. Needs a key: set TWELVEDATA_API_KEY. This is the ONE place a
secret enters the pipeline - it lives in CI secrets and is used only at build
time, never shipped to the browser (principle 5).

Reserved as the US reliability fallback when yfinance is flaky:
    PRICE_PROVIDER_US=twelvedata
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from core.interfaces import Quote, PriceProvider

_API = "https://api.twelvedata.com/time_series"


def _td_symbol(symbol: str, market: str) -> str:
    return f"{symbol}:NSE" if market == "IN" else symbol


class TwelveDataPrices(PriceProvider):
    id = "twelvedata"
    markets = ("IN", "US")

    def get_quotes(self, symbols, history_days):
        key = os.environ.get("TWELVEDATA_API_KEY")
        symbols = list(symbols)
        if not key:
            return [Quote(symbol=s["symbol"], market=s["market"], close=0, prev_close=0,
                          currency="INR" if s["market"] == "IN" else "USD",
                          ok=False, error="TWELVEDATA_API_KEY not set") for s in symbols]

        out = []
        for i, s in enumerate(symbols):
            sym, market = s["symbol"], s["market"]
            currency = "INR" if market == "IN" else "USD"
            params = urllib.parse.urlencode({
                "symbol": _td_symbol(sym, market), "interval": "1day",
                "outputsize": max(history_days, 7), "apikey": key, "order": "ASC",
            })
            try:
                with urllib.request.urlopen(f"{_API}?{params}", timeout=30) as r:
                    data = json.load(r)
                if data.get("status") == "error":
                    raise ValueError(data.get("message", "api error"))
                hist = [{"date": v["datetime"], "close": float(v["close"])}
                        for v in data.get("values", [])]
                if not hist:
                    raise ValueError("no rows returned")
                close = hist[-1]["close"]
                prev = hist[-2]["close"] if len(hist) > 1 else close
                out.append(Quote(symbol=sym, market=market, close=close,
                                 prev_close=prev, currency=currency, history=hist))
            except Exception as e:
                out.append(Quote(symbol=sym, market=market, close=0, prev_close=0,
                                 currency=currency, ok=False, error=str(e)[:200]))
            if i < len(symbols) - 1:
                time.sleep(8)  # stay under the 8 req/min free-tier ceiling
        return out

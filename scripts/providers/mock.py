"""Deterministic offline adapters (principle 12).

Selected when PRICE_PROVIDER_*/NEWS_PROVIDER/FX_PROVIDER = "mock", or simply via
`python fetch.py --mock`. Series are derived from a hash of the symbol, so every
run produces identical data with zero network and zero keys - ideal for tests,
CI smoke checks, and previewing the site from a clean checkout.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

from core.interfaces import Quote, NewsItem, PriceProvider, NewsProvider, FxProvider


def _seed(text: str) -> float:
    """Stable pseudo-random float in [0, 1) from a string."""
    h = hashlib.sha256(text.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class MockPrices(PriceProvider):
    id = "mock"
    markets = ("IN", "US")

    def get_quotes(self, symbols, history_days):
        out = []
        for s in symbols:
            sym = s["symbol"]
            currency = "INR" if s["market"] == "IN" else "USD"
            base = 50 + _seed(sym) * (2500 if currency == "INR" else 400)
            drift = (_seed(sym + "d") - 0.45) * 0.004     # slight up/down bias
            vol = 0.012 + _seed(sym + "v") * 0.02
            days = min(history_days, 180)
            start = date.today() - timedelta(days=days)
            hist, price = [], base
            for i in range(days):
                wobble = math.sin(i / 6.0 + _seed(sym) * 6) * vol
                price = max(1.0, price * (1 + drift + wobble * 0.4))
                hist.append({"date": (start + timedelta(days=i)).isoformat(),
                             "close": round(price, 4)})
            close = hist[-1]["close"]
            prev = hist[-2]["close"] if len(hist) > 1 else close
            out.append(Quote(symbol=sym, market=s["market"], close=close,
                             prev_close=prev, currency=currency, history=hist))
        return out


class MockNews(NewsProvider):
    id = "mock"

    def get_market_news(self, feeds, limit):
        return [NewsItem(
            title=f"Markets close mixed as sectors diverge (sample {i + 1})",
            url="https://example.com/market-news",
            source="Mock Wire",
            published=f"2026-07-1{i % 9}T09:30:00Z",
        ) for i in range(min(limit, 6))]

    def get_symbol_news(self, symbol, name, limit):
        return [NewsItem(
            title=f"{name} in focus after quarterly update (sample)",
            url="https://example.com/" + symbol.lower(),
            source="Mock Wire",
            published="2026-07-10T14:00:00Z",
            symbol=symbol,
        )]


class MockFx(FxProvider):
    id = "mock"

    def get_rate(self, base, quote):
        table = {("USD", "INR"): 83.2, ("INR", "USD"): 1 / 83.2}
        return table.get((base, quote), 1.0)

    def get_rate_series(self, base, quote, start_date):
        # Deterministic daily history so lot-based cost basis works offline.
        rate = self.get_rate(base, quote)
        if not rate or rate == 1.0:
            return {}
        try:
            sd = date.fromisoformat(start_date[:10])
        except (ValueError, TypeError):
            return {}
        out, d, today = {}, sd, date.today()
        while d <= today:
            wobble = 1 + 0.01 * math.sin((d - sd).days / 20.0)
            out[d.isoformat()] = round(rate * wobble, 4)
            d += timedelta(days=1)
        return out

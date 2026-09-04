"""FX adapters for converting holdings into the base currency (see docs/adr/0004).

Two keyless options:
  - yfinance (default): reads the `USDINR=X` style pair from Yahoo; reuses the
    same dependency as the default price adapter, so no extra install.
  - exchangerate_host: a keyless HTTP fallback. Note (verified 2026-07):
    exchangerate.host itself now gates its endpoints behind a free access key,
    so this adapter targets the still-keyless `open.er-api.com` service, which
    returns the same shape of data. Selected with FX_PROVIDER=exchangerate_host.

Neither raises fatally to the pipeline: fetch.py wraps the call and falls back to
a 1.0 rate if FX is unreachable, so native-currency figures stay correct and the
build always completes (principle 13).
"""
from __future__ import annotations

import json
import urllib.request

from core.interfaces import FxProvider


class YFinanceFx(FxProvider):
    id = "yfinance"

    def get_rate(self, base, quote):
        if base == quote:
            return 1.0
        import yfinance as yf
        pair = f"{base}{quote}=X"
        df = yf.Ticker(pair).history(period="5d", interval="1d")
        if df is None or df.empty:
            raise ValueError(f"no FX data for {pair}")
        closes = df["Close"].dropna()
        if closes.empty:
            raise ValueError(f"no FX close for {pair}")
        return float(closes.iloc[-1])

    def get_rate_series(self, base, quote, start_date):
        if base == quote:
            return {}
        import yfinance as yf
        pair = f"{base}{quote}=X"
        df = yf.Ticker(pair).history(start=start_date, interval="1d")
        if df is None or df.empty:
            return {}
        return {idx.date().isoformat(): float(v)
                for idx, v in df["Close"].dropna().items()}


class ExchangerateHostFx(FxProvider):
    # Keyless spot rates only; no free historical endpoint, so get_rate_series
    # inherits the base {} (lot cost basis then falls back to today's rate).
    id = "exchangerate_host"
    _API = "https://open.er-api.com/v6/latest"

    def get_rate(self, base, quote):
        if base == quote:
            return 1.0
        with urllib.request.urlopen(f"{self._API}/{base}", timeout=30) as r:
            data = json.load(r)
        rate = (data.get("rates") or {}).get(quote)
        if not rate:
            raise ValueError(f"no FX rate {base}->{quote}")
        return float(rate)

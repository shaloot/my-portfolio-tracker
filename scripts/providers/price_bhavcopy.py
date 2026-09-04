"""Official NSE end-of-day adapter (keyless, India only).

Pulls the same EOD data NSE publishes in its daily *bhavcopy*, via the
maintained `jugaad-data` library, which absorbs NSE's periodic URL/cookie
changes and anti-scraping headers for you (hand-rolling those requests is the
classic way this breaks - see docs/adr/0002).

Use it as the India provider with  PRICE_PROVIDER_IN=bhavcopy .
US symbols are rejected - pair it with yfinance/twelvedata for US.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from core.interfaces import Quote, PriceProvider


def _ensure_jugaad_cache():
    """Pre-create jugaad-data's on-disk cache dir with exist_ok=True.

    jugaad-data 0.33.1 caches each request under `user_cache_dir(app, app)` but
    creates that dir with a non-idempotent `os.makedirs()` guarded by a
    check-then-create race. Looping over several symbols (or its own internal
    per-range calls) trips that race with an "[Errno 17] File exists". Creating
    the dir ourselves first means jugaad's `if not os.path.exists(...)` is
    already False, so it never runs the racy branch. Best-effort - failure here
    just falls back to jugaad's own behaviour.
    """
    try:
        from appdirs import user_cache_dir
        for app in ("nsehistory-stock", "nsehistory-index"):
            env_dir = os.environ.get("J_CACHE_DIR")
            cache_dir = (os.path.join(env_dir, app) if env_dir
                         else user_cache_dir(app, app))
            os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        pass


class BhavcopyPrices(PriceProvider):
    id = "bhavcopy"
    markets = ("IN",)

    def get_quotes(self, symbols, history_days):
        from jugaad_data.nse import stock_df  # lazy import

        _ensure_jugaad_cache()
        out = []
        to_d = date.today()
        # Pad the window generously so weekends/holidays still leave enough sessions.
        from_d = to_d - timedelta(days=max(history_days, 10) + 15)
        for s in symbols:
            sym, market = s["symbol"], s["market"]
            if market != "IN":
                out.append(Quote(symbol=sym, market=market, close=0, prev_close=0,
                                 currency="USD", ok=False,
                                 error="bhavcopy serves Indian equities only"))
                continue
            try:
                df = stock_df(symbol=sym, from_date=from_d, to_date=to_d, series="EQ")
                if df is None or df.empty:
                    raise ValueError("no rows returned")
                df = df.sort_values("DATE")
                hist = [{"date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                         "close": float(c)}
                        for d, c in zip(df["DATE"], df["CLOSE"])]
                close = hist[-1]["close"]
                prev = hist[-2]["close"] if len(hist) > 1 else close
                out.append(Quote(symbol=sym, market="IN", close=close,
                                 prev_close=prev, currency="INR", history=hist))
            except Exception as e:
                out.append(Quote(symbol=sym, market="IN", close=0, prev_close=0,
                                 currency="INR", ok=False, error=str(e)[:200]))
        return out

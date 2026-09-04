"""Provider selection: env var wins, else the config default.

This is the seam that makes principle 3 real. The three places that must agree:
  - env  : PRICE_PROVIDER_IN / PRICE_PROVIDER_US / NEWS_PROVIDER / FX_PROVIDER
  - code : the adapter classes registered in the tables below
  - docs : docs/adr/0002, 0003, 0004 record the alternatives + rationale

Swapping a provider = change the env value. No pipeline code changes.
"""
from __future__ import annotations

import os

from providers.price_yfinance import YFinancePrices
from providers.price_bhavcopy import BhavcopyPrices
from providers.price_twelvedata import TwelveDataPrices
from providers.news_rss import RssNews
from providers.fx import YFinanceFx, ExchangerateHostFx


PRICE_ADAPTERS = {
    "yfinance": YFinancePrices,
    "bhavcopy": BhavcopyPrices,
    "twelvedata": TwelveDataPrices,
}
NEWS_ADAPTERS = {"rss": RssNews}
FX_ADAPTERS = {"yfinance": YFinanceFx, "exchangerate_host": ExchangerateHostFx}

# Defaults, chosen for "most liberal free tier, keyless" per the ADRs.
DEFAULT_PRICE_IN = "yfinance"   # bhavcopy is the official-data upgrade (also keyless)
DEFAULT_PRICE_US = "yfinance"   # twelvedata (800/day, keyed) is the documented fallback
DEFAULT_NEWS = "rss"
DEFAULT_FX = "yfinance"


def _pick(env_key: str, table: dict, default: str):
    choice = os.environ.get(env_key, default)
    if choice not in table:
        valid = ", ".join(sorted(table))
        raise SystemExit(f"{env_key}={choice!r} is not a known provider. Valid: {valid}")
    return choice, table[choice]()


def price_provider_for(market: str):
    env_key = "PRICE_PROVIDER_IN" if market == "IN" else "PRICE_PROVIDER_US"
    default = DEFAULT_PRICE_IN if market == "IN" else DEFAULT_PRICE_US
    return _pick(env_key, PRICE_ADAPTERS, default)


def news_provider():
    return _pick("NEWS_PROVIDER", NEWS_ADAPTERS, DEFAULT_NEWS)


def fx_provider():
    return _pick("FX_PROVIDER", FX_ADAPTERS, DEFAULT_FX)

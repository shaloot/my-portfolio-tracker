"""Fixed provider contracts.

Every price, news, or FX source is an adapter that implements one of these
interfaces. Because the pipeline only ever talks to the interface, swapping a
provider is a config change (which class the registry hands back), never a
rewrite. See docs/adr/0002 (prices), 0003 (news), 0004 (fx).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Quote:
    """End-of-day quote for one symbol, priced in the symbol's own currency."""

    symbol: str
    market: str                     # "IN" or "US"
    close: float                    # latest EOD close
    prev_close: float               # previous session close (drives day change)
    currency: str                   # "INR" or "USD"
    history: list[dict] = field(default_factory=list)  # [{date, close}] oldest->newest
    ok: bool = True                 # False => could not fetch; row renders "stale"
    error: str | None = None        # short human-readable reason when not ok


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str                  # ISO8601 string (or "" if the feed omits it)
    symbol: str | None = None       # attached holding, or None for market news


class PriceProvider(ABC):
    """Returns EOD quotes for a set of symbols in ONE market."""

    #: short id used in env/config/logs, e.g. "yfinance"
    id: str = "base"
    #: markets this adapter can serve
    markets: tuple[str, ...] = ()

    @abstractmethod
    def get_quotes(self, symbols: Iterable[dict], history_days: int) -> list[Quote]:
        """symbols: iterable of {symbol, market, name}. Returns one Quote each.

        A well-behaved adapter never raises for a single bad symbol: it returns
        a Quote with ok=False so the build continues (principle 13).
        """
        raise NotImplementedError


class NewsProvider(ABC):
    id: str = "base"

    @abstractmethod
    def get_market_news(self, feeds: list[str], limit: int) -> list[NewsItem]:
        raise NotImplementedError

    @abstractmethod
    def get_symbol_news(self, symbol: str, name: str, limit: int) -> list[NewsItem]:
        raise NotImplementedError


class FxProvider(ABC):
    id: str = "base"

    @abstractmethod
    def get_rate(self, base: str, quote: str) -> float:
        """Units of `quote` per 1 unit of `base`, e.g. get_rate('USD','INR') ~ 83."""
        raise NotImplementedError

    def get_rate_series(self, base: str, quote: str, start_date: str) -> dict[str, float]:
        """Optional: daily historical rates {date_iso: rate} from `start_date` to
        today, used to value each purchase lot at the FX rate on its own date.

        Default returns {} ("no history available"), in which case the pipeline
        falls back to today's rate for cost basis. Adapters that can serve history
        (e.g. yfinance) override this.
        """
        return {}

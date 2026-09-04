"""RSS news adapter - the default: keyless and effectively unlimited.

Market headlines come from the feeds listed in config/settings.json. Per-holding
news uses Google News' keyless RSS search per company name, which returns clean
company-specific items with no API key or quota (see docs/adr/0003).
"""
from __future__ import annotations

import html
import re
import urllib.parse

from core.interfaces import NewsItem, NewsProvider

_GNEWS = "https://news.google.com/rss/search"


def _entries(url: str):
    import feedparser  # lazy: --mock needs nothing installed
    return feedparser.parse(url).entries


def _clean(s: str) -> str:
    """Decode HTML entities and strip stray tags some feeds leave in titles."""
    s = html.unescape(s or "").strip()
    s = re.sub(r"<[^>]+>", "", s)          # drop any residual markup
    return html.unescape(s).strip()        # some feeds double-encode (e.g. day&amp;#39;s)


def _to_item(e, source: str, symbol=None) -> NewsItem:
    src = getattr(getattr(e, "source", None), "title", None) or source
    return NewsItem(
        title=_clean(getattr(e, "title", "")),
        url=getattr(e, "link", "") or "",
        source=_clean(src),
        published=getattr(e, "published", "") or getattr(e, "updated", "") or "",
        symbol=symbol,
    )


class RssNews(NewsProvider):
    id = "rss"

    def get_market_news(self, feeds, limit):
        items, seen = [], set()
        for url in feeds:
            try:
                entries = _entries(url)
            except Exception:
                continue  # a dead feed must not sink the others (principle 13)
            for e in entries:
                it = _to_item(e, source="Markets")
                if it.title and it.url and it.url not in seen:
                    seen.add(it.url)
                    items.append(it)
        return items[:limit]

    def get_symbol_news(self, symbol, name, limit):
        q = urllib.parse.urlencode({"q": f'"{name}" stock', "hl": "en-IN",
                                    "gl": "IN", "ceid": "IN:en"})
        items = []
        for e in _entries(f"{_GNEWS}?{q}"):
            it = _to_item(e, source="Google News", symbol=symbol)
            if it.title:
                items.append(it)
            if len(items) >= limit:
                break
        return items

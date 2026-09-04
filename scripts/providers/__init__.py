"""Provider adapters. Each implements a fixed interface from core.interfaces
and is selected by the registry via an env var. Heavy deps (yfinance, feedparser,
jugaad-data) are imported lazily inside methods so `--mock` needs nothing installed.
"""

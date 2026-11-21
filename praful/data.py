"""Market data for this strategy: Yahoo 5-minute futures candles in New York time.

Gold: COMEX gold futures `GC=F` (Yahoo has no spot XAUUSD). SMT partner: silver `SI=F`.
Yahoo keeps about the last 60 days of 5-minute data. Futures trade almost 24 hours
(Sunday 18:00 to Friday 17:00 New York time, daily break 17:00-18:00).
"""
from __future__ import annotations

import pandas as pd

NY = "America/New_York"


def fetch(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(symbol, period=period, interval=interval, progress=False,
                     auto_adjust=False, multi_level_index=False)
    if df is None or df.empty:
        raise SystemExit(f"yfinance returned no data for {symbol}.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna().copy()
    idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    df.index = idx.tz_convert(NY)
    return df[~df.index.duplicated(keep="last")].sort_index()

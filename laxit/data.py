"""Market data for this strategy: download from yfinance or load a CSV, in IST."""
from __future__ import annotations

from datetime import time

import pandas as pd

IST = "Asia/Kolkata"


def fetch_yf(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    """Intraday OHLC from the unofficial yfinance API (5m/2m history is limited to 60 days)."""
    import yfinance as yf

    df = yf.download(symbol, period=period, interval=interval, progress=False,
                     auto_adjust=False, multi_level_index=False)
    if df is None or df.empty:
        raise SystemExit(f"yfinance returned no data for {symbol}. "
                         "Check network access to query1/query2.finance.yahoo.com.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def load_csv(path: str) -> pd.DataFrame:
    """CSV with a Datetime (or Date/Time/Timestamp) column plus Open, High, Low, Close."""
    df = pd.read_csv(path)
    tcol = next(c for c in df.columns if c.lower() in ("datetime", "date", "time", "timestamp"))
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep OHLC, convert to IST, drop duplicates and candles outside the NSE session."""
    df = df[["Open", "High", "Low", "Close"]].dropna().copy()
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    df.index = idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    df = df[(t >= time(9, 15)) & (t <= time(15, 25))]  # regular NSE session, bar start times
    return df

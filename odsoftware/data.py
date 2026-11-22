"""Market data for this strategy: 3-minute NSE candles in IST.

Two sources:
  * yfinance (default): 1-minute candles grouped into 3-minute candles starting at 09:15
    (09:15, 09:18, ...), the same grid TradingView uses for NSE. yfinance has no 3-minute
    interval and keeps 1-minute data for only about the last 30 days (7 days per request).
  * CSV (--csv): e.g. the TradingView export written by tv_download/download.mjs
    (Datetime, Open, High, Low, Close, ...). These are the exact candles of the client's
    chart and give about 2 months of 3-minute history. A 3-minute CSV is used as it is
    (the Muhurat session has its own time grid on TradingView); 1-minute CSVs are grouped.

Session: TradingView's NSE:NIFTY 3-minute data has no candles after 15:15 (last candle
15:12), while Yahoo goes on to 15:29. The 5 extra Yahoo candles a day shift the SMA/DEMA, so
candles from 15:15 on are dropped to match the chart.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

IST = "Asia/Kolkata"
SESSION_START = time(9, 15)
SESSION_END = time(15, 15)       # TradingView NSE:NIFTY: last 3-minute candle starts 15:12


def fetch_1m(symbol: str, days: int = 30) -> pd.DataFrame:
    """Last `days` calendar days of 1-minute OHLC from yfinance, fetched in 7-day chunks."""
    import yfinance as yf

    end = pd.Timestamp.now(tz=IST).normalize() + pd.Timedelta(days=1)
    start_all = end - pd.Timedelta(days=min(days, 29) + 1)
    parts = []
    s = start_all
    while s < end:
        e = min(s + pd.Timedelta(days=7), end)
        df = yf.download(symbol, start=s.strftime("%Y-%m-%d"), end=e.strftime("%Y-%m-%d"),
                         interval="1m", progress=False, auto_adjust=False, multi_level_index=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            parts.append(df)
        s = e
    if not parts:
        raise SystemExit(f"yfinance returned no 1-minute data for {symbol}. "
                         "Check network access to query1/query2.finance.yahoo.com.")
    return pd.concat(parts)


def load_csv(path: str) -> pd.DataFrame:
    """CSV with a Datetime (or Date/Time/Timestamp) column plus Open, High, Low, Close.

    Times without a UTC offset are read as IST.
    """
    df = pd.read_csv(path)
    tcol = next(c for c in df.columns if c.lower() in ("datetime", "date", "time", "timestamp"))
    df[tcol] = pd.to_datetime(df[tcol], utc=False)
    df = df.set_index(tcol)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep OHLC, convert to IST, drop duplicates and candles outside 09:15-15:15."""
    df = df[["Open", "High", "Low", "Close"]].dropna().copy()
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    df.index = idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    return df[(t >= SESSION_START) & (t < SESSION_END)]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Group candles into `minutes`-minute candles labelled by their start time.

    Bins start at midnight IST, so for 3 minutes they fall on 09:15, 09:18, ... (555 % 3 == 0).
    """
    out = df.resample(f"{minutes}min", origin="start_day", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    t = out.index.time
    return out[(t >= SESSION_START) & (t < SESSION_END)]


def to_timeframe(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Candles of `minutes` minutes: data already at that timeframe is kept as it is."""
    step = pd.Series(df.index).diff().dt.total_seconds().div(60).median()
    return df if step == minutes else resample(df, minutes)

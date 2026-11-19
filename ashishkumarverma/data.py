"""Market data for this strategy: 1-minute yfinance spot data (IST).

The 1-minute candles are used to detect the live breakout, stop loss and target, and are
grouped into 15-minute candles from 09:15 (09:15, 09:30, ...) for the ORB and alert candles,
the same grid TradingView uses for NSE.
yfinance keeps 1-minute data for about the last 30 days, at most 7 days per request.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

IST = "Asia/Kolkata"


def fetch_1m(symbol: str, days: int = 7) -> pd.DataFrame:
    """Last `days` calendar days of 1-minute OHLC, fetched in 7-day chunks."""
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
    """CSV with a Datetime (or Date/Time/Timestamp) column plus Open, High, Low, Close, Volume."""
    df = pd.read_csv(path)
    tcol = next(c for c in df.columns if c.lower() in ("datetime", "date", "time", "timestamp"))
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep OHLC + Volume, convert to IST, drop duplicates and candles outside 09:15-15:30."""
    cols = ["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df.columns else [])
    df = df[cols].dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if "Volume" not in df.columns:
        df["Volume"] = float("nan")
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    df.index = idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    return df[(t >= time(9, 15)) & (t < time(15, 30))]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Group candles into `minutes`-minute candles labelled by their start time.

    Bins start at midnight IST, so 15-minute bins fall on 09:15, 09:30, ... (555 % 15 == 0).
    """
    out = df.resample(f"{minutes}min", origin="start_day", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Open", "High", "Low", "Close"])
    t = out.index.time
    return out[(t >= time(9, 15)) & (t < time(15, 30))]

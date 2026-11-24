"""Market data for this strategy: Yahoo's 15-minute OHLCV for the last ~60 days (IST).

All rules run on these 15-minute candles (09:15, 09:30, ... grid): levels, RVOL, 9 EMA,
breakout entry, stop loss and square-off.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

IST = "Asia/Kolkata"


def fetch_15m(symbol: str) -> pd.DataFrame:
    """Yahoo's own 15-minute OHLCV for the last 60 days (used for the 20-day RVOL history)."""
    import yfinance as yf

    df = yf.download(symbol, period="60d", interval="15m", progress=False, auto_adjust=False,
                     multi_level_index=False)
    if df is None or df.empty:
        raise SystemExit(f"yfinance returned no 15-minute data for {symbol}.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


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

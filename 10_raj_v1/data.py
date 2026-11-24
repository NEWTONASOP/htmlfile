"""Market data for this strategy: NIFTY 50 candles (2 or 5 minutes) in IST.

Sources:
  * yfinance (default): `^NSEI` at the strategy's interval. Yahoo keeps 2m and 5m data for
    about the last 60 calendar days (2m: about 30 sessions in practice).
  * CSV (--csv): Datetime, Open, High, Low, Close (IST if no offset), e.g. a TradingView or
    broker export. Candles finer than the timeframe are grouped; equal ones are used as they are.

Session: TradingView's NSE:NIFTY has no candles after 15:15 while Yahoo goes on to 15:29, so
candles starting at 15:15 or later are dropped to match the chart's indicator values.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

IST = "Asia/Kolkata"
SESSION_START = time(9, 15)
SESSION_END = time(15, 15)


def fetch_yf(symbol: str, minutes: int) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(symbol, period="59d", interval=f"{minutes}m", progress=False,
                     auto_adjust=False, multi_level_index=False)
    if df is None or df.empty:
        raise SystemExit(f"yfinance returned no {minutes}m data for {symbol}. "
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
    """Keep OHLC (rounded to 0.01), convert to IST, drop duplicates and candles outside 09:15-15:15."""
    df = df[["Open", "High", "Low", "Close"]].dropna().astype(float).round(2)   # Yahoo float32 noise
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    df.index = idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    return df[(t >= SESSION_START) & (t < SESSION_END)]


def to_timeframe(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Candles of `minutes` minutes starting 09:15; data already at that timeframe is kept."""
    step = pd.Series(df.index).diff().dt.total_seconds().div(60).median()
    if step == minutes:
        return df
    out = df.resample(f"{minutes}min", origin="start_day", offset="15min", label="left",
                      closed="left").agg({"Open": "first", "High": "max", "Low": "min",
                                          "Close": "last"}).dropna()
    t = out.index.time
    return out[(t >= SESSION_START) & (t < SESSION_END)]

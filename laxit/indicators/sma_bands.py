"""SMA 20 High / SMA 20 Low - simple moving averages (TradingView ta.sma).

SMA 20 High = average of the last 20 candle highs.
SMA 20 Low  = average of the last 20 candle lows.
Every candle has equal weight (simple, not smoothed/RMA).
"""
from __future__ import annotations

import pandas as pd

LENGTH = 20


def sma(src: pd.Series, n: int) -> pd.Series:
    """Pine ta.sma."""
    return src.rolling(n).mean()


def sma_bands(df: pd.DataFrame, n: int = LENGTH) -> pd.DataFrame:
    return pd.DataFrame({"sma_h": sma(df["High"], n), "sma_l": sma(df["Low"], n)}, index=df.index)

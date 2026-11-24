"""SMA 120 on close (TradingView ta.sma).

BUY condition : candle close above SMA 120.
SELL condition: candle close below SMA 120.
"""
from __future__ import annotations

import pandas as pd

LENGTH = 120
SOURCE = "Close"


def sma(df: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    return df[SOURCE].rolling(n).mean().rename(f"sma{n}")

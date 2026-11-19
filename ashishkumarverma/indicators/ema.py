"""9 EMA of the 15-minute closes (TradingView / FYERS EMA), continuing across days.

Exit rule: CE exits after a 15-minute candle closes BELOW the 9 EMA, PE after a candle
closes ABOVE it (exit at the next 15-minute candle open).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LENGTH = 9


def pine_ema(src: pd.Series, n: int) -> pd.Series:
    """Pine ta.ema: alpha = 2/(n+1), seeded with the SMA of the first n values."""
    v = src.to_numpy(float)
    out = np.full(len(v), np.nan)
    if len(v) >= n:
        out[n - 1] = v[:n].mean()
        a = 2 / (n + 1)
        for i in range(n, len(v)):
            out[i] = a * v[i] + (1 - a) * out[i - 1]
    return pd.Series(out, index=src.index)


def ema(df: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    return pine_ema(df["Close"], n).rename(f"ema{n}")

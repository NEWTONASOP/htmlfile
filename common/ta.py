"""TradingView-compatible indicator building blocks shared by the strategies."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pine_ema(src: pd.Series, n: int) -> pd.Series:
    """Pine ta.ema: alpha = 2/(n+1), seeded with the SMA of the first n values."""
    v = src.to_numpy(float)
    out = np.full(len(v), np.nan)
    start = np.flatnonzero(~np.isnan(v))
    if len(start) == 0 or len(v) - start[0] < n:
        return pd.Series(out, index=src.index)
    s0 = start[0]
    out[s0 + n - 1] = v[s0:s0 + n].mean()
    a = 2 / (n + 1)
    for i in range(s0 + n, len(v)):
        out[i] = a * v[i] + (1 - a) * out[i - 1]
    return pd.Series(out, index=src.index)


def sma(src: pd.Series, n: int) -> pd.Series:
    """Pine ta.sma."""
    return src.rolling(n).mean()

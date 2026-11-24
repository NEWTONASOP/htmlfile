"""RSI on close (TradingView ta.rsi): Wilder smoothing (ta.rma) of gains and losses."""
from __future__ import annotations

import numpy as np
import pandas as pd

LENGTH = 21
BULL_ABOVE = 60.0      # RSI > 60 = bullish
BEAR_BELOW = 45.0      # RSI < 45 = bearish


def pine_rma(v: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.rma: alpha = 1/n, seeded with the SMA of the first n non-na values."""
    out = np.full(len(v), np.nan)
    start = np.flatnonzero(~np.isnan(v))
    if len(start) == 0 or len(v) - start[0] < n:
        return out
    s0 = start[0]
    out[s0 + n - 1] = v[s0:s0 + n].mean()
    for i in range(s0 + n, len(v)):
        out[i] = (v[i] + (n - 1) * out[i - 1]) / n
    return out


def rsi(df: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    c = df["Close"].to_numpy(float)
    ch = np.full(len(c), np.nan)
    ch[1:] = np.diff(c)
    up = pine_rma(np.where(np.isnan(ch), np.nan, np.maximum(ch, 0)), n)
    dn = pine_rma(np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0)), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(dn == 0, 100.0, np.where(up == 0, 0.0, 100 - 100 / (1 + up / dn)))
    out[np.isnan(up) | np.isnan(dn)] = np.nan
    return pd.Series(out, index=df.index, name="rsi")

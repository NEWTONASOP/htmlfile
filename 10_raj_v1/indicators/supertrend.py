"""Supertrend (TradingView ta.supertrend / built-in "Supertrend": ATR Length 10, Factor 3).

Port of Pine's reference implementation (hl2 source, ta.atr = RMA of true range):

    upperBand = hl2 + factor * atr,  lowerBand = hl2 - factor * atr
    lowerBand := lowerBand > lowerBand[1] or close[1] < lowerBand[1] ? lowerBand : lowerBand[1]
    upperBand := upperBand < upperBand[1] or close[1] > upperBand[1] ? upperBand : upperBand[1]
    direction  = na(atr[1]) ? 1 : superTrend[1] == upperBand[1] ? (close > upperBand ? -1 : 1)
                                                                : (close < lowerBand ? 1 : -1)
    superTrend = direction == -1 ? lowerBand : upperBand

direction -1 = uptrend (green line below price, bullish); +1 = downtrend (red line above, bearish).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .rsi import pine_rma

ATR_LENGTH = 10
FACTOR = 3.0


def atr(df: pd.DataFrame, n: int) -> np.ndarray:
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(pc), h - l, np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))))
    return pine_rma(tr, n)


def supertrend(df: pd.DataFrame, atr_length: int = ATR_LENGTH, factor: float = FACTOR) -> pd.DataFrame:
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    a = atr(df, atr_length)
    hl2 = (h + l) / 2
    n = len(c)
    up, lo = np.full(n, np.nan), np.full(n, np.nan)
    st, dirn = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        if np.isnan(a[i]):
            continue
        u, d = hl2[i] + factor * a[i], hl2[i] - factor * a[i]
        if i > 0 and not np.isnan(a[i - 1]):
            pl, pu = lo[i - 1], up[i - 1]
            d = d if (d > pl or c[i - 1] < pl) else pl
            u = u if (u < pu or c[i - 1] > pu) else pu
            if st[i - 1] == pu:
                dirn[i] = -1 if c[i] > u else 1
            else:
                dirn[i] = 1 if c[i] < d else -1
        else:
            dirn[i] = 1                                   # na(atr[1])
        up[i], lo[i] = u, d
        st[i] = d if dirn[i] == -1 else u
    return pd.DataFrame({"supertrend": st, "st_dir": dirn}, index=df.index)

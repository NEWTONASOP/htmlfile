"""Fast MA of OD SOFTWARE: DEMA 20 on close (TradingView ta.dema).

Decoded from the script's inputs ("Fast MA Length" 20, "Fast MA type" DEMA, "Fast Source"
close) and checked against the script's own "Fast MA" plot on NSE:NIFTY 3m.

ta.dema(src, n) = 2 * ema1 - ema2, where ema1 = ta.ema(src, n) and ema2 = ta.ema(ema1, n).
ta.ema is seeded with the SMA of its first n values (Pine behaviour), so ema2 starts once
n values of ema1 exist.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LENGTH = 20
SOURCE = "Close"


def pine_ema(src: pd.Series, n: int) -> pd.Series:
    """Pine ta.ema: alpha = 2/(n+1), seeded with the SMA of the first n non-na values."""
    v = src.to_numpy(float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) == 0 or len(v) - valid[0] < n:
        return pd.Series(out, index=src.index)
    s0 = valid[0]
    out[s0 + n - 1] = v[s0:s0 + n].mean()
    a = 2 / (n + 1)
    for i in range(s0 + n, len(v)):
        out[i] = a * v[i] + (1 - a) * out[i - 1]
    return pd.Series(out, index=src.index)


def dema(df: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    e1 = pine_ema(df[SOURCE], n)
    e2 = pine_ema(e1, n)
    return (2 * e1 - e2).rename(f"dema{n}")

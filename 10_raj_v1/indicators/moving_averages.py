"""SMA and EMA on close (TradingView ta.sma / ta.ema). Type and period of each line are settings."""
from __future__ import annotations

import numpy as np
import pandas as pd

SOURCE = "Close"


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


def moving_average(df: pd.DataFrame, ma_type: str, n: int) -> pd.Series:
    src = df[SOURCE]
    if ma_type == "sma":
        out = src.rolling(n).mean()            # Pine ta.sma
    elif ma_type == "ema":
        out = pine_ema(src, n)                 # Pine ta.ema
    else:
        raise ValueError(f"unknown MA type {ma_type!r} (use 'sma' or 'ema')")
    return out.rename(f"{ma_type}{n}")

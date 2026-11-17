"""Rakesh Rattan EMA set - 7 EMAs of close (TradingView ta.ema), 5-minute chart.

| EMA | Colour on chart          |
|-----|--------------------------|
| 15  | Blue (short-term)        |
| 30  | Sky Blue                 |
| 35  | Yellow                   |
| 40  | Green                    |
| 45  | Dark Blue                |
| 50  | Red                      |
| 60  | Black (main / longest)   |

Crossover of the 60 EMA through all the others:
  bull: the 60 EMA is below every other EMA (all faster EMAs have crossed above it)
  bear: the 60 EMA is above every other EMA
A BUY/SELL signal is the first candle on which that state becomes true.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SOURCE = "Close"
FAST_LENGTHS = [15, 30, 35, 40, 45, 50]
MAIN_LENGTH = 60


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


def ema_set(df: pd.DataFrame) -> pd.DataFrame:
    """Columns ema15 ... ema60, bull/bear state and fresh bull_cross / bear_cross."""
    out = pd.DataFrame(index=df.index)
    for n in FAST_LENGTHS + [MAIN_LENGTH]:
        out[f"ema{n}"] = pine_ema(df[SOURCE], n)
    fast = out[[f"ema{n}" for n in FAST_LENGTHS]]
    main = out[f"ema{MAIN_LENGTH}"]
    bull = main < fast.min(axis=1)
    bear = main > fast.max(axis=1)
    out["bull_state"], out["bear_state"] = bull, bear
    out["bull_cross"] = bull & ~bull.shift(1, fill_value=True)
    out["bear_cross"] = bear & ~bear.shift(1, fill_value=True)
    return out


def warmup_bars() -> int:
    return 3 * MAIN_LENGTH

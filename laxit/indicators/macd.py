"""MACD - Python port of the TradingView built-in (original source: macd.pine).

Settings: source close, fast 12, slow 26, signal 9, EMA for both oscillator and signal.
MACD = EMA12(close) - EMA26(close); signal = EMA9(MACD); histogram = MACD - signal.
A bullish crossover is the histogram moving from <= 0 to > 0 (MACD crossing above
the signal line), a bearish one from >= 0 to < 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SOURCE = "Close"
FAST, SLOW, SIGNAL = 12, 26, 9


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


def macd(df: pd.DataFrame, fast: int = FAST, slow: int = SLOW, signal: int = SIGNAL) -> pd.DataFrame:
    """Columns: macd, macd_sig, macd_hist, bull_cross, bear_cross."""
    src = df[SOURCE]
    m = pine_ema(src, fast) - pine_ema(src, slow)
    sig = pine_ema(m, signal)
    above, below = m > sig, m < sig
    return pd.DataFrame({
        "macd": m,
        "macd_sig": sig,
        "macd_hist": m - sig,
        "bull_cross": above & ~above.shift(1, fill_value=True),   # ta.crossover(macd, signal)
        "bear_cross": below & ~below.shift(1, fill_value=True),   # ta.crossunder(macd, signal)
    }, index=df.index)


def warmup_bars() -> int:
    return 5 * SLOW

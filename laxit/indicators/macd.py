"""MACD - Python port of the TradingView built-in (original source: macd.pine).

Settings: source close, fast 12, slow 26, signal 9, EMA for both oscillator and signal.
MACD = EMA12(close) - EMA26(close); signal = EMA9(MACD); histogram = MACD - signal.
A bullish crossover is the histogram moving from <= 0 to > 0 (MACD crossing above
the signal line), a bearish one from >= 0 to < 0.
"""
from __future__ import annotations

import pandas as pd

from common.ta import pine_ema  # Pine ta.ema (SMA-seeded)

SOURCE = "Close"
FAST, SLOW, SIGNAL = 12, 26, 9


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

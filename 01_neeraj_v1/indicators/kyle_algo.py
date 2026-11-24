"""Kyle Algo v1 - EMA ribbon (Python port of the part the strategy uses).

Original Pine source: kyle_algo.pine (same folder).

The strategy uses only the EMA ribbon: 15 EMAs of HIGH with lengths 9, 12, ..., 51.
The inputs below (sensitivity, Keltner length, ATR length, factor) drive only the
Supertrend BUY/SELL labels and candle colours, which the strategy ignores, so they
do not change any trade. They are kept here to document the chart settings.
"""
from __future__ import annotations

import pandas as pd

SENSITIVITY = 1.7
KELTNER_LENGTH = 11
ATR_LENGTH = 10
FACTOR = 1.0

RIBBON_LENGTHS = list(range(9, 52, 3))  # 9, 12, ..., 51 -> 15 EMAs of high


def ema(src: pd.Series, n: int) -> pd.Series:
    """Pine ta.ema (alpha = 2/(n+1)). The seed difference vanishes after warm-up."""
    return src.ewm(span=n, adjust=False).mean()


def ema_ribbon(df: pd.DataFrame) -> pd.DataFrame:
    """Top and bottom of the ribbon: highest and lowest of the 15 EMAs of high."""
    ribbon = pd.concat([ema(df["High"], n) for n in RIBBON_LENGTHS], axis=1)
    return pd.DataFrame({"ribbon_top": ribbon.max(axis=1), "ribbon_bot": ribbon.min(axis=1)},
                        index=df.index)


def warmup_bars() -> int:
    return 3 * max(RIBBON_LENGTHS)

"""RVOL (relative volume), length 20 - as used for the FYERS RVOL filter.

FYERS does not publish its formula, so the standard definition is used:
    RVOL = volume of the candle / average volume of the last 20 candles (including this one)
on 15-minute candles, continuing across days (so the 09:15 candle is compared with the
previous day's candles). A value of 1.5 means 50% more volume than the recent average.
"""
from __future__ import annotations

import pandas as pd

LENGTH = 20
MIN_RVOL = 1.5


def rvol(df: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    vol = df["Volume"].astype(float)
    return (vol / vol.rolling(n).mean()).rename("rvol")

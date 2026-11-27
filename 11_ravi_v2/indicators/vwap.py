"""VWAP (TradingView built-in "VWAP", source: vwap.pine).

Anchor "Session" (resets on the first candle of each day), source hlc3:
    vwap = cumulative(hlc3 * volume) / cumulative(volume) since the session's first candle.
Applied to the option premium's 5-minute candles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def vwap(df: pd.DataFrame) -> pd.Series:
    src = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].astype(float)
    day = pd.Series(df.index.date, index=df.index)
    pv = (src * vol).groupby(day).cumsum()
    v = vol.groupby(day).cumsum()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = pv / v
    return out.where(v > 0).rename("vwap")

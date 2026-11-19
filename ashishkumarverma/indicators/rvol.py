"""RVOL (relative volume), length 20 - FYERS RVOL as confirmed by the client (option B).

Time-of-day RVOL on 15-minute candles:
    RVOL = volume of the candle
           / average volume of the SAME 15-minute slot over the previous 20 trading days
e.g. today's 09:15 candle vs the 09:15 candles of the last 20 days (today not included).
A value of 1.5 means 50% more volume than usual for that time of day.

The 20-day history comes from Yahoo's 15-minute bars (60 days kept). Both the candle volume
and the average come from the same source so the ratio is consistent.

rvol_rolling() is the other common definition (average of the last 20 candles), kept for
comparison (--rvol-mode candles).
"""
from __future__ import annotations

import pandas as pd

LENGTH = 20
MIN_RVOL = 1.5


def rvol_slot(df15: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    """Volume / mean volume of the same time slot over the previous n days (NaN if fewer)."""
    vol = df15["Volume"].astype(float)
    slot = df15.index.strftime("%H:%M")
    avg = vol.groupby(slot).transform(lambda s: s.shift(1).rolling(n, min_periods=n).mean())
    return (vol / avg).rename("rvol")


def rvol_rolling(df15: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    vol = df15["Volume"].astype(float)
    return (vol / vol.rolling(n).mean()).rename("rvol")

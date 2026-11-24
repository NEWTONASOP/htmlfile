"""Smoothed Heiken Ashi Candles v1 - Python port (original source: smoothed_heiken_ashi.pine).

Default settings: len 10, len2 10.
  o, c, h, l  = EMA 10 of open, close, high, low
  haclose     = (o + h + l + c) / 4
  haopen      = (haopen[1] + haclose[1]) / 2   (first value (o + c) / 2)
  hahigh/low  = max/min of h/l with haopen and haclose
  o2, c2, h2, l2 = EMA 10 of haopen, haclose, hahigh, halow   -> the plotted candle
Colour: RED when o2 > c2, otherwise GREEN (lime).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

LEN = 10
LEN2 = 10


def pine_ema(src: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.ema with SMA seed, starting at the first non-na value."""
    out = np.full(len(src), np.nan)
    ok = np.flatnonzero(~np.isnan(src))
    if len(ok) == 0 or len(src) - ok[0] < n:
        return out
    s0 = ok[0]
    out[s0 + n - 1] = src[s0:s0 + n].mean()
    a = 2 / (n + 1)
    for i in range(s0 + n, len(src)):
        out[i] = a * src[i] + (1 - a) * out[i - 1]
    return out


def smoothed_heiken_ashi(df: pd.DataFrame, n1: int = LEN, n2: int = LEN2) -> pd.DataFrame:
    """Columns ha_open, ha_high, ha_low, ha_close (plotted candle) and ha_green (bool)."""
    o, c, h, l = (pine_ema(df[k].to_numpy(float), n1) for k in ("Open", "Close", "High", "Low"))
    haclose = (o + h + l + c) / 4
    haopen = np.full(len(df), np.nan)
    for i in range(len(df)):
        prev = haopen[i - 1] if i > 0 else math.nan
        haopen[i] = (o[i] + c[i]) / 2 if math.isnan(prev) else (prev + haclose[i - 1]) / 2
    hahigh = np.maximum(h, np.maximum(haopen, haclose))     # na-propagating like Pine v2 max()
    halow = np.minimum(l, np.minimum(haopen, haclose))
    o2, c2, h2, l2 = (pine_ema(x, n2) for x in (haopen, haclose, hahigh, halow))
    red = o2 > c2
    return pd.DataFrame({"ha_open": o2, "ha_high": h2, "ha_low": l2, "ha_close": c2,
                         "ha_green": ~red & ~np.isnan(o2)}, index=df.index)

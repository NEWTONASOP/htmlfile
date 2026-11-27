"""ADX (TradingView built-in "Average directional index", source: adx.pine).

    up = change(high), down = -change(low)
    +DM = up > down and up > 0 ? up : 0,  -DM = down > up and down > 0 ? down : 0
    tr  = ta.rma(ta.tr, DI length)           (ta.tr is na on the first candle)
    +DI = fixnan(100 * rma(+DM) / tr),  -DI = fixnan(100 * rma(-DM) / tr)
    ADX = 100 * rma(|+DI - -DI| / (+DI + -DI, or 1 if 0), ADX smoothing)
Defaults: ADX smoothing 14, DI length 14. Applied to the option premium's 5-minute candles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ADX_SMOOTHING = 14
DI_LENGTH = 14


def pine_rma(v: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.rma: alpha = 1/n, seeded with the SMA of the first n non-na values."""
    out = np.full(len(v), np.nan)
    ok = np.flatnonzero(~np.isnan(v))
    if len(ok) == 0 or len(v) - ok[0] < n:
        return out
    s0 = ok[0]
    out[s0 + n - 1] = v[s0:s0 + n].mean()
    for i in range(s0 + n, len(v)):
        out[i] = (v[i] + (n - 1) * out[i - 1]) / n
    return out


def _fixnan(v: np.ndarray) -> np.ndarray:
    return pd.Series(v).ffill().to_numpy()


def adx(df: pd.DataFrame, adx_len: int = ADX_SMOOTHING, di_len: int = DI_LENGTH) -> pd.Series:
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    up = np.r_[np.nan, np.diff(h)]
    down = np.r_[np.nan, -np.diff(l)]
    plus_dm = np.where(np.isnan(up), np.nan, np.where((up > down) & (up > 0), up, 0.0))
    minus_dm = np.where(np.isnan(down), np.nan, np.where((down > up) & (down > 0), down, 0.0))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(pc), np.nan, np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))))
    trur = pine_rma(tr, di_len)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus = _fixnan(100 * pine_rma(plus_dm, di_len) / trur)
        minus = _fixnan(100 * pine_rma(minus_dm, di_len) / trur)
        s = plus + minus
        dx = np.abs(plus - minus) / np.where(s == 0, 1, s)
    return pd.Series(100 * pine_rma(dx, adx_len), index=df.index, name="adx")

"""OD SOFTWARE trade signal: ATR trailing stop on EMA 4 of close (ATR 7 x 1.7).

Decoded from the script's own Strategy-Tester trades. Inputs st_emaPer 4, TrPer 7, st_factor 1.7
are the only inputs that move its entries (checked by changing every input on TradingView).

    src   = ta.ema(close, 4)
    nLoss = 1.7 * ta.atr(7)                       (ta.atr = RMA of true range)
    trail = src > trail[1] and src[1] > trail[1] ? max(trail[1], src - nLoss)
          : src < trail[1] and src[1] < trail[1] ? min(trail[1], src + nLoss)
          : src > trail[1] ? src - nLoss : src + nLoss
    BUY  = src crosses above trail,  SELL = src crosses below trail   (always alternate)

On NSE:NIFTY 3m (21 Sep - 20 Nov 2026) these give exactly the script's 152 entries.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from .dema import pine_ema
except ImportError:  # imported as a top-level module
    from dema import pine_ema

EMA_LEN = 4
ATR_LEN = 7
FACTOR = 1.7


def pine_atr(df: pd.DataFrame, n: int) -> np.ndarray:
    """ta.atr: RMA of the true range (first bar: high - low), seeded with the SMA of n values."""
    h, lo, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    tr = np.empty(len(c))
    tr[0] = h[0] - lo[0]
    tr[1:] = np.maximum.reduce([h[1:] - lo[1:], np.abs(h[1:] - c[:-1]), np.abs(lo[1:] - c[:-1])])
    out = np.full(len(c), np.nan)
    if len(c) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(c)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def atr_trail(df: pd.DataFrame, ema_len: int = EMA_LEN, atr_len: int = ATR_LEN,
              factor: float = FACTOR) -> pd.DataFrame:
    """Columns: trail_src (EMA), trail, trail_buy, trail_sell."""
    src = pine_ema(df["Close"], ema_len).to_numpy()
    nloss = factor * pine_atr(df, atr_len)
    n = len(src)
    ts = np.zeros(n)                      # Pine nz(trail[1]) = 0 before the first value
    for i in range(1, n):
        p, x, x1 = ts[i - 1], src[i], src[i - 1]
        if np.isnan(nloss[i]) or np.isnan(x):
            continue
        if x > p and x1 > p:
            ts[i] = max(p, x - nloss[i])
        elif x < p and x1 < p:
            ts[i] = min(p, x + nloss[i])
        elif x > p:
            ts[i] = x - nloss[i]
        else:
            ts[i] = x + nloss[i]
    s1, t1 = np.r_[np.nan, src[:-1]], np.r_[np.nan, ts[:-1]]
    valid = ~np.isnan(nloss) & ~np.isnan(src)
    return pd.DataFrame({
        "trail_src": src,
        "trail": np.where(valid, ts, np.nan),
        "trail_buy": (src > ts) & (s1 <= t1),
        "trail_sell": (src < ts) & (s1 >= t1),
    }, index=df.index)

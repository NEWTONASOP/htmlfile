"""Reversal Entry Zones [trade_w_samet] - Python port of the signal engine.

Original Pine source: reversal_entry_zones.pine (same folder).
Settings used: Sensitivity preset "Low", Swing Source "Average", other inputs default
(Average Length 5, ATR Length 5, Minimum Absolute Reversal 0.05, Extra Confirmation Bars 0).

Engine: track the running high (EMA 5 of high) while swinging up and the running low
(EMA 5 of low) while swinging down. A reversal is confirmed when price comes back by at least
    threshold = max(close * 0.015 / 100, max(0.05, 2.8 * ATR(5)))
Confirmed high -> "Bearish Reversal", confirmed low -> "Bullish Reversal".
"Last Signal" (the status panel row) is the direction of the latest confirmed reversal:
    +1 = Bullish Reversal (BUY condition), -1 = Bearish Reversal (SELL condition), 0 = Waiting.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

PRESETS = {"Low": (2.8, 0.015), "Very Low": (3.5, 0.02)}   # (ATR multiple, % of close)
PRESET = "Low"
SOURCE = "Average"
AVG_LEN = 5
ATR_LEN = 5
CUSTOM_ABS = 0.05
CONFIRM_BARS = 0


def pine_ema(src: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.ema: alpha = 2/(n+1), seeded with the SMA of the first n values."""
    out = np.full(len(src), np.nan)
    if len(src) < n:
        return out
    out[n - 1] = src[:n].mean()
    a = 2 / (n + 1)
    for i in range(n, len(src)):
        out[i] = a * src[i] + (1 - a) * out[i - 1]
    return out


def pine_atr(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.atr: RMA (alpha 1/n, SMA seed) of the true range (high-low on the first bar)."""
    prev_c = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(prev_c), h - lo,
                  np.maximum(h - lo, np.maximum(np.abs(h - prev_c), np.abs(lo - prev_c))))
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def reversal_entry_zones(df: pd.DataFrame, preset: str = PRESET, source: str = SOURCE) -> pd.DataFrame:
    """Columns: rez_last (+1/-1/0 after this candle), rez_signal (+1/-1 on the confirming
    candle), rez_pivot_idx (bar of the confirmed pivot), rez_price (raw high/low there)."""
    H, Lo, C = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    n = len(df)
    atr_mult, pct = PRESETS[preset]
    atr = pine_atr(H, Lo, C, ATR_LEN)
    hi_base = H if source == "High/Low" else pine_ema(H, AVG_LEN)
    lo_base = Lo if source == "High/Low" else pine_ema(Lo, AVG_LEN)
    k = CONFIRM_BARS

    last = np.zeros(n, int)
    sig = np.zeros(n, int)
    piv_idx = np.full(n, -1)
    piv_px = np.full(n, np.nan)

    run_high = run_low = run_high_raw = run_low_raw = math.nan
    run_high_bar = run_low_bar = -1
    swing = 1
    last_dir = 0
    for i in range(n):
        j = i - k
        hi_ref = hi_base[j] if j >= 0 else math.nan
        lo_ref = lo_base[j] if j >= 0 else math.nan
        a = atr[i]
        thr = math.nan if math.isnan(a) else max(C[i] * pct / 100.0, max(CUSTOM_ABS, atr_mult * a))
        if not math.isnan(hi_ref) and not math.isnan(lo_ref):
            if math.isnan(run_high) or math.isnan(run_low):
                run_high, run_low = hi_ref, lo_ref
                run_high_raw, run_low_raw = H[j], Lo[j]
                run_high_bar = run_low_bar = j
                swing = 1
            if swing == 1:
                if hi_ref > run_high:
                    run_high, run_high_raw, run_high_bar = hi_ref, H[j], j
                if run_high - lo_ref >= thr:                 # False while thr is na
                    sig[i], piv_idx[i], piv_px[i] = -1, run_high_bar, run_high_raw
                    last_dir = -1
                    swing = -1
                    run_low, run_low_raw, run_low_bar = lo_ref, Lo[j], j
            else:
                if lo_ref < run_low:
                    run_low, run_low_raw, run_low_bar = lo_ref, Lo[j], j
                if hi_ref - run_low >= thr:
                    sig[i], piv_idx[i], piv_px[i] = 1, run_low_bar, run_low_raw
                    last_dir = 1
                    swing = 1
                    run_high, run_high_raw, run_high_bar = hi_ref, H[j], j
        last[i] = last_dir

    return pd.DataFrame({"rez_last": last, "rez_signal": sig, "rez_pivot_idx": piv_idx,
                         "rez_price": piv_px}, index=df.index)

"""Pivot Points High Low & Missed Reversal Levels [LuxAlgo] - Python port.

Original Pine source: luxalgo_pivots.pine (same folder), © LuxAlgo, CC BY-NC-SA 4.0.
Default settings: Pivot Length 50, regular and missed pivots shown.

Regular pivots are ta.pivothigh/ta.pivotlow(50, 50): confirmed 50 candles after the pivot
candle. Missed pivots (the ghost labels) are only created on the candle where a regular
pivot confirms, and always sit before that regular pivot on the chart. So the latest
CONFIRMED pivot (normal or missed) is always the latest regular pivot:
    state +1 = latest confirmed pivot is a LOW  (BUY condition)
    state -1 = latest confirmed pivot is a HIGH (SELL condition)
The provisional ghost drawn only on the live last candle (barstate.islast) is not a
confirmed pivot and is ignored.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

LENGTH = 50


def _pmax(a: float, b: float) -> float:
    """Pine math.max: na if either argument is na."""
    return math.nan if (math.isnan(a) or math.isnan(b)) else max(a, b)


def _pmin(a: float, b: float) -> float:
    return math.nan if (math.isnan(a) or math.isnan(b)) else min(a, b)


def pivots(high: np.ndarray, low: np.ndarray, L: int):
    """ta.pivothigh/ta.pivotlow(L, L) values on the confirmation bar (nan otherwise).

    Ties: strictly beyond the L bars on the left, at least equal to the L bars on the right.
    """
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for t in range(2 * L, n):
        p = t - L
        if high[p] > high[p - L:p].max() and high[p] >= high[p + 1:t + 1].max():
            ph[t] = high[p]
        if low[p] < low[p - L:p].min() and low[p] <= low[p + 1:t + 1].min():
            pl[t] = low[p]
    return ph, pl


def lux_pivots(df: pd.DataFrame, L: int = LENGTH):
    """Returns (state Series, events DataFrame).

    events: one row per label the indicator draws, in the order it draws them:
        confirm_idx (bar where it is drawn), pivot_idx (bar it points at), price,
        kind ("high"/"low"), missed (bool).
    """
    H, Lo = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    n = len(df)
    ph, pl = pivots(H, Lo, L)

    mx = mn = fmx = fmn = 0.0                  # var max = 0., var min = 0., follow_* = 0.
    mx_x1 = mn_x1 = fmx_x1 = fmn_x1 = 0
    os_ = 0
    prev = dict(mx=mx, mn=mn, fmx=fmx, fmn=fmn)
    state = np.zeros(n, int)
    have = False
    events = []

    for i in range(n):
        hl = H[i - L] if i >= L else math.nan
        ll = Lo[i - L] if i >= L else math.nan
        os_prev = os_

        mx = _pmax(hl, mx)
        mn = _pmin(ll, mn)
        fmx = _pmax(hl, fmx)
        fmn = _pmin(ll, fmn)
        if mx > prev["mx"]:
            mx_x1 = i - L
            fmn = ll
        if mn < prev["mn"]:
            mn_x1 = i - L
            fmx = hl
        if fmn < prev["fmn"]:
            fmn_x1 = i - L
        if fmx > prev["fmx"]:
            fmx_x1 = i - L

        def add(x, y, kind, missed):
            if not math.isnan(y):
                events.append(dict(confirm_idx=i, pivot_idx=x, price=y, kind=kind, missed=missed))

        if not math.isnan(ph[i]) and ph[i] != 0:
            if os_prev == 1:
                add(mn_x1, mn, "low", True)
            elif ph[i] < mx:
                add(mx_x1, mx, "high", True)
                add(fmn_x1, fmn, "low", True)
            add(i - L, ph[i], "high", False)
            os_, mx, mn, have = 1, ph[i], ph[i], True
        if not math.isnan(pl[i]) and pl[i] != 0:
            if os_prev == 0:
                add(mx_x1, mx, "high", True)
            elif pl[i] > mn:
                add(fmx_x1, fmx, "high", True)
                add(mn_x1, mn, "low", True)
            add(i - L, pl[i], "low", False)
            os_, mx, mn, have = 0, pl[i], pl[i], True

        prev = dict(mx=mx, mn=mn, fmx=fmx, fmn=fmn)
        state[i] = 0 if not have else (-1 if os_ == 1 else 1)

    ev = pd.DataFrame(events, columns=["confirm_idx", "pivot_idx", "price", "kind", "missed"])
    return pd.Series(state, index=df.index, name="lux_state"), ev

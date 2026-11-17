"""Liquidity Swings [LuxAlgo] - Python port of the zones the strategy uses.

Original Pine source: liquidity_swings.pine (same folder), © LuxAlgo, CC BY-NC-SA 4.0.

Settings: Pivot Lookback 14, Swing Area "Wick Extremity", Filter Areas By "Count", 0.
With the Count filter a zone box is only drawn once a later candle trades back into
the zone (count crosses above 0). Swings that are never revisited before the next
swing of the same side are never drawn.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PIVOT_LOOKBACK = 14
SWING_AREA = "Wick Extremity"
FILTER_BY = "Count"
FILTER_VALUE = 0


def pivots(high: np.ndarray, low: np.ndarray, L: int):
    """Pine-style ta.pivothigh/ta.pivotlow(L, L).

    Returns boolean arrays flagged on the CONFIRMATION bar (pivot bar + L).
    Ties: the pivot must be strictly beyond the L bars on its left and at least
    equal to the L bars on its right.
    """
    n = len(high)
    ph = np.zeros(n, bool)
    pl = np.zeros(n, bool)
    for t in range(2 * L, n):
        p = t - L
        h, lo = high[p], low[p]
        if h > high[p - L:p].max() and h >= high[p + 1:t + 1].max():
            ph[t] = True
        if lo < low[p - L:p].min() and lo <= low[p + 1:t + 1].min():
            pl[t] = True
    return ph, pl


def visible_zones(o, h, lo, c, conf, L: int, high_side: bool) -> dict:
    """Port of get_counts/set_zone with Filter = Count.

    When a pivot confirms (bar j = pivot + L) its count resets to 0. On each later
    bar, the candle L bars back is counted if it trades inside the zone
    (low < top and high > btm). The zone box is only drawn when the count crosses
    above the filter value (0), i.e. when price first revisits the zone. If the
    next pivot of the same side confirms first, the zone is never drawn.
    Returns arrays: appear (box drawn on this bar), swing (flag on the pivot
    candle of a drawn zone), pivot_idx/top/btm (set on the appear bar).
    """
    n = len(h)
    appear, swing = np.zeros(n, bool), np.zeros(n, bool)
    pivot_idx = np.full(n, -1)
    top_a, btm_a = np.full(n, np.nan), np.full(n, np.nan)
    p = top = btm = None
    count = 0
    for j in range(n):
        if conf[j]:
            p, count = j - L, 0
            if high_side:   # Wick Extremity
                top, btm = h[p], max(o[p], c[p])
            else:
                top, btm = min(o[p], c[p]), lo[p]
            continue
        if p is None:
            continue
        k = j - L
        if lo[k] < top and h[k] > btm:
            count += 1
            if count == 1 and FILTER_VALUE < 1:  # ta.crossover(count, filterValue=0)
                appear[j], swing[p] = True, True
                pivot_idx[j], top_a[j], btm_a[j] = p, top, btm
    return dict(appear=appear, swing=swing, pivot_idx=pivot_idx, top=top_a, btm=btm_a)


def liquidity_zones(df: pd.DataFrame, L: int = PIVOT_LOOKBACK) -> pd.DataFrame:
    """Columns per side (red = swing high, green = swing low):
    <side>_zone        zone box drawn on this candle (known live)
    <side>_swing       swing candle of a zone that gets drawn (box start; hindsight)
    <side>_pivot_time  swing candle time, on the candle where the box appears
    <side>_top/_btm    zone bounds, on the candle where the box appears
    """
    o, h, lo, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    ph, pl = pivots(h, lo, L)
    out = pd.DataFrame(index=df.index)
    for color, conf in (("red", ph), ("green", pl)):
        z = visible_zones(o, h, lo, c, conf, L, high_side=(color == "red"))
        out[f"{color}_zone"] = z["appear"]
        out[f"{color}_swing"] = z["swing"]
        out[f"{color}_pivot_time"] = pd.Series(z["pivot_idx"]).map(
            lambda k: df.index[int(k)] if k >= 0 else pd.NaT).to_numpy()
        out[f"{color}_top"], out[f"{color}_btm"] = z["top"], z["btm"]
    return out

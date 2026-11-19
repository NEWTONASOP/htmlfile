"""Opening range, gap and alert candle for one day, from 15-minute candles.

Opening candle : 09:15-09:30 -> Opening High / Opening Low.
Gap            : today's 09:15 open vs the previous day's close.
Alert candle   : the FIRST 15-minute candle after the opening candle, at any time of day,
                 that CLOSES above Opening High (CE) or below Opening Low (PE).
                 Its high/low are the breakout levels.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

OPEN_START = time(9, 15)


def day_levels(c15_day: pd.DataFrame, prev_close: float) -> dict:
    """Levels and setup for one day. c15_day must contain rvol and ema columns."""
    t = c15_day.index.time
    first = c15_day[t == OPEN_START]
    if first.empty:
        return dict(setup=None, note="Opening candle missing")
    o = first.iloc[0]
    lv = dict(open_high=o.High, open_low=o.Low, open_rvol=o.rvol, day_open=o.Open,
              prev_close=prev_close,
              gap_pct=(o.Open / prev_close - 1) * 100 if prev_close == prev_close else float("nan"),
              setup=None, alert_time=None, alert_high=None, alert_low=None, alert_close=None,
              alert_rvol=None, note="")
    for ts, c in c15_day[t > OPEN_START].iterrows():
        side = "CE" if c.Close > o.High else "PE" if c.Close < o.Low else None
        if side:
            lv.update(setup=side, alert_time=ts, alert_high=c.High, alert_low=c.Low,
                      alert_close=c.Close, alert_rvol=c.rvol)
            break
    if lv["setup"] is None:
        lv["note"] = "No candle closed outside the opening range"
    return lv

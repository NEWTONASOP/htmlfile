"""Opening Range Breakout levels from 15-minute candles.

ORB candle   : 09:15-09:30 IST -> ORB High / ORB Low.
Alert candle : 09:30-09:45 IST -> Alert High / Alert Low, and its close decides the setup:
    close > ORB High -> "CE" (bullish)
    close < ORB Low  -> "PE" (bearish)
    otherwise        -> None (no trade for the day)
"""
from __future__ import annotations

from datetime import time

import pandas as pd

ORB_START = time(9, 15)
ALERT_START = time(9, 30)


def orb_levels(c15: pd.DataFrame) -> pd.DataFrame:
    """One row per day from 15-minute candles of that day (index = candle start time)."""
    rows = []
    for day, d in c15.groupby(c15.index.date):
        t = d.index.time
        orb, alert = d[t == ORB_START], d[t == ALERT_START]
        if orb.empty or alert.empty:
            rows.append(dict(date=day, setup=None, note="ORB or alert candle missing"))
            continue
        o, a = orb.iloc[0], alert.iloc[0]
        if a.Close > o.High:
            setup, note = "CE", "Alert close above ORB High"
        elif a.Close < o.Low:
            setup, note = "PE", "Alert close below ORB Low"
        else:
            setup, note = None, "Alert close inside ORB: no trade"
        rows.append(dict(date=day, orb_high=o.High, orb_low=o.Low, alert_open=a.Open,
                         alert_high=a.High, alert_low=a.Low, alert_close=a.Close,
                         setup=setup, note=note))
    return pd.DataFrame(rows).set_index("date")

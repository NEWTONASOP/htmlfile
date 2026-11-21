"""NIFTY weekly expiry and strike selection.

Weekly expiry: Tuesday (NSE NIFTY weekly expiry day). If that Tuesday is a market holiday,
expiry moves to the previous trading day. "Next weekly expiry" from a given day is the
nearest expiry on or after that day, so on expiry day itself today's expiry is used.
Strike: nearest valid NIFTY strike (multiple of 50) to spot + 200 (CE) or spot - 200 (PE).
"""
from __future__ import annotations

import datetime as dt

EXPIRY_WEEKDAY = 1          # Monday = 0, Tuesday = 1
STRIKE_STEP = 50
OTM_POINTS = 200


def expiry_for(day: dt.date, trading_days: list[dt.date]) -> dt.date:
    """Weekly expiry used for a trade entered on `day`."""
    known = set(trading_days)
    last_known = max(trading_days)
    start = day
    while True:
        tue = start + dt.timedelta(days=(EXPIRY_WEEKDAY - start.weekday()) % 7)
        exp = tue
        if tue <= last_known:
            while exp not in known:                 # holiday -> previous trading day
                exp -= dt.timedelta(days=1)
        if exp >= day:
            return exp
        start = tue + dt.timedelta(days=1)          # adjusted expiry already passed


def strike_for(spot: float, is_call: bool) -> float:
    target = spot + OTM_POINTS if is_call else spot - OTM_POINTS
    return float(round(target / STRIKE_STEP) * STRIKE_STEP)

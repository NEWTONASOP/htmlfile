#!/usr/bin/env python3
"""Independent check of the last RAVI v1 run (results/trades.csv) on the cached Angel One data.

1. Indicators recomputed with plain pandas (ewm/groupby), not the strategy's Pine ports:
   EMA 9/7 (ewm), session VWAP (hlc3 x volume), ADX 14/14 (ewm alpha 1/14). Compared after
   300 candles of warm-up, where the different seeding has faded.
2. Every trade re-checked: signal close beyond its range (range = latest 09:20/10:00/.../15:00
   candle), ATM strike, morning/afternoon conditions, entry = next option open, exit
   re-simulated (SL 20, trail 10/10, 7 EMA exit, 15:20), one at a time, max 2 per range,
   second trade on the same side only after NIFTY closed back out of that side.

Usage: python 11_ravi_v1/verify.py
"""
from __future__ import annotations

import math
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RANGES = [time(9, 20), time(10, 0), time(11, 0), time(12, 0), time(13, 0), time(14, 0), time(15, 0)]
BAR = pd.Timedelta(minutes=5)


def load(name):
    df = pd.read_csv(DATA / f"{name}.csv", index_col=0, parse_dates=True)
    df.index = pd.DatetimeIndex(df.index).tz_convert("Asia/Kolkata")
    return df


def ind(o):
    o = o.copy()
    o["e9"] = o.Close.ewm(span=9, adjust=False).mean()
    o["e7"] = o.Close.ewm(span=7, adjust=False).mean()
    hlc3 = (o.High + o.Low + o.Close) / 3
    g = o.index.date
    o["vw"] = (hlc3 * o.Volume).groupby(g).cumsum() / o.Volume.groupby(g).cumsum()
    up, dn = o.High.diff(), -o.Low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([o.High - o.Low, (o.High - o.Close.shift()).abs(), (o.Low - o.Close.shift()).abs()], axis=1).max(axis=1)
    w = lambda s: pd.Series(s, index=o.index).ewm(alpha=1 / 14, adjust=False).mean()  # noqa: E731
    atr = w(tr)
    p, m = 100 * w(pdm) / atr, 100 * w(mdm) / atr
    o["ax"] = 100 * w((p - m).abs() / (p + m).replace(0, 1))
    return o


def main():
    nifty = load("nifty_5m")
    nifty["e9"] = nifty.Close.ewm(span=9, adjust=False).mean()
    tl = pd.read_csv(HERE / "results" / "trades.csv")
    errs, maxdiff = [], {"ema9": 0, "ema7": 0, "vwap": 0, "adx": 0}
    import sys
    sys.path.insert(0, str(HERE))
    from strategy import prepare
    _, _, opts = prepare(9)
    for sym, o in opts.items():
        x = ind(o).iloc[300:]
        if x.empty:
            continue
        for k, a, b in (("ema9", "ema_m", "e9"), ("ema7", "ema7", "e7"), ("vwap", "vwap", "vw"), ("adx", "adx", "ax")):
            maxdiff[k] = max(maxdiff[k], float(np.nanmax(np.abs(x[a] - x[b]))))
    print("Indicator max abs diff vs pandas recompute:", {k: round(v, 6) for k, v in maxdiff.items()})

    prev = None
    count = {}
    for _, t in tl.iterrows():
        day = pd.Timestamp(t.day).date()
        sig = pd.Timestamp(f"{t.day} {t.signal}").tz_localize("Asia/Kolkata")
        ent = sig + BAR
        nb = nifty[nifty.index.date == day]
        rt = max(r for r in RANGES if r < sig.time())
        rc = nb[nb.index.time == rt].iloc[0]
        c = nifty.at[sig, "Close"]
        side_ok = c > rc.High if t.side == "CE" else c < rc.Low
        o = ind(opts[t.option])
        ob = o.loc[sig]
        aft = rt >= time(13, 0)
        conds = [side_ok, abs(t.strike - math.floor(c / 50 + 0.5) * 50) < 1e-9,
                 (c > nifty.at[sig, "e9"]) if t.side == "CE" else (c < nifty.at[sig, "e9"]),
                 ob.Close > ob.e9, ob.ax >= 20 - 0.5]
        if not aft:
            conds.append(ob.Close > ob.vw)
        if not all(conds):
            errs.append(f"{t.day} {t.signal} conditions {conds}")
        if abs(t.entry - o.at[ent, "Open"]) > 1e-6:
            errs.append(f"{t.day} {t.signal} entry price")
        sl, best, flag, ex = t.entry - 20, t.entry, False, None
        for ts in o.loc[ent:].index:
            b = o.loc[ts]
            if flag:
                ex = (ts, b.Open); break
            if b.Low <= sl:
                ex = (ts, min(b.Open, sl)); break
            best = max(best, b.High)
            sl = max(sl, t.entry - 20 + 10 * math.floor((best - t.entry) / 10 + 1e-9))
            if (ts + BAR).time() >= time(15, 20):
                ex = (ts, b.Close); break
            if b.Close < opts[t.option].at[ts, "ema7"]:
                flag = True
        if ex is None or ex[0].strftime("%H:%M") != t.exit_time or abs(ex[1] - t.exit) > 1e-6:
            errs.append(f"{t.day} {t.signal} exit {ex} vs {t.exit_time} {t.exit}")
        key = (t.day, t["range"])
        count[key] = count.get(key, 0) + 1
        if prev is not None and prev.day == t.day:
            pe = pd.Timestamp(f"{prev.day} {prev.exit_time}").tz_localize("Asia/Kolkata")
            if ent <= pe:
                errs.append(f"{t.day} {t.signal} overlaps previous trade")
            if prev["range"] == t["range"] and prev.side == t.side:
                pent = pd.Timestamp(f"{prev.day} {prev.entry_time}").tz_localize("Asia/Kolkata")
                seg = nb.loc[pent:sig - BAR].Close
                back = (seg <= rc.High).any() if t.side == "CE" else (seg >= rc.Low).any()
                if not back:
                    errs.append(f"{t.day} {t.signal} same-side re-entry without a fresh break")
        prev = t
    if max(count.values(), default=0) > 2:
        errs.append("more than 2 trades in a range")
    print(f"Trades checked: {len(tl)}, rule violations: {len(errs)}")
    for e in errs:
        print("  ", e)


if __name__ == "__main__":
    main()

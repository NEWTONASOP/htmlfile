#!/usr/bin/env python3
"""Independent check of the last RAVI v2 run (results/trades.csv) on the cached Angel One data.

1. Indicators recomputed with plain pandas (ewm/groupby): EMA 20, session VWAP (hlc3 x volume),
   ADX 14/14 (ewm alpha 1/14). Compared after 300 candles of warm-up.
2. Every trade re-checked: window range recomputed (14:55 window = 14:55 + 15:00 candles), signal
   close beyond it, ATM strike, VWAP (windows 1-4) / EMA 20 / ADX >= 20 on the option, entry =
   next option open, exit re-simulated (SL 20, target 50, trail after +20 at high - 10, close below
   EMA 7 -> next open, 15:20, or
   reversal at the next trade's entry), max 1 CE + 1 PE per window, max 6 trades a day.

Usage: python 11_ravi_v2/verify.py
"""
from __future__ import annotations

import math
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BAR = pd.Timedelta(minutes=5)
WIN = {"09:20": ["09:20"], "10:00": ["10:00"], "11:00": ["11:00"], "12:00": ["12:00"], "13:00": ["13:00"],
       "14:00": ["14:00"], "14:55": ["14:55", "15:00"]}


def ind(o):
    o = o.copy()
    o["e20"] = o.Close.ewm(span=20, adjust=False).mean()
    o["e7"] = o.Close.ewm(span=7, adjust=False).mean()
    hlc3 = (o.High + o.Low + o.Close) / 3
    g = o.index.date
    o["vw"] = (hlc3 * o.Volume).groupby(g).cumsum() / o.Volume.groupby(g).cumsum()
    up, dn = o.High.diff(), -o.Low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([o.High - o.Low, (o.High - o.Close.shift()).abs(), (o.Low - o.Close.shift()).abs()], axis=1).max(axis=1)
    w = lambda s: pd.Series(s, index=o.index).ewm(alpha=1 / 14, adjust=False).mean()  # noqa: E731
    p, m = 100 * w(pdm) / w(tr), 100 * w(mdm) / w(tr)
    o["ax"] = 100 * w((p - m).abs() / (p + m).replace(0, 1))
    return o


def main():
    sys.path.insert(0, str(HERE))
    from strategy import prepare, load_cached
    import types
    _, _, opts = prepare(types.SimpleNamespace(ema=20, adx_len=14))
    nifty = load_cached("nifty_5m")
    diff = {"ema20": 0.0, "vwap": 0.0, "adx": 0.0}
    for o in opts.values():
        x = ind(o).iloc[300:]
        for k, a, b in (("ema20", "ema", "e20"), ("vwap", "vwap", "vw"), ("adx", "adx", "ax")):
            if len(x):
                diff[k] = max(diff[k], float(np.nanmax(np.abs(x[a] - x[b]))))
    print("Indicator max abs diff vs pandas recompute:", {k: round(v, 6) for k, v in diff.items()})

    tl = pd.read_csv(HERE / "results" / "trades.csv")
    errs = []
    ts = lambda d, hm: pd.Timestamp(f"{d} {hm}").tz_localize("Asia/Kolkata")  # noqa: E731
    for k, t in tl.iterrows():
        nb = nifty[nifty.index.date == pd.Timestamp(t.day).date()]
        rc = nb[nb.index.strftime("%H:%M").isin(WIN[t.window])]
        sig, ent = ts(t.day, t.signal), ts(t.day, t.entry_time)
        c = nifty.at[sig, "Close"]
        o = ind(opts[t.option])
        ob = o.loc[sig]
        ok = [(c > rc.High.max()) if t.side == "CE" else (c < rc.Low.min()),
              t.strike == math.floor(c / 50 + 0.5) * 50, ob.Close > ob.e20, ob.ax >= 19.5,
              t.window >= "13:00" or ob.Close > ob.vw, ent == sig + BAR, abs(t.entry - o.at[ent, "Open"]) < 1e-6,
              ent.time() <= time(15, 15)]
        if not all(ok):
            errs.append(f"{t.day} {t.signal} entry checks {ok}")
        if t.reason == "Reversal":
            nxt = tl.iloc[k + 1]
            if not (nxt.day == t.day and nxt.entry_time == t.exit_time and nxt.side != t.side):
                errs.append(f"{t.day} {t.signal} reversal not followed by the opposite entry")
            continue
        sl, best, ex, flag = t.entry - 20, t.entry, None, False
        for bt in o.loc[ent:].index:
            b = o.loc[bt]
            if flag:
                ex = (bt, b.Open); break
            if b.Low <= sl:
                ex = (bt, min(b.Open, sl)); break
            if b.High >= t.entry + 50:
                ex = (bt, max(b.Open, t.entry + 50)); break
            best = max(best, b.High)
            if best - t.entry >= 20:
                sl = max(sl, best - 10)
            if b.Close <= sl:
                ex = (bt, sl); break
            if (bt + BAR).time() >= time(15, 20):
                ex = (bt, b.Close); break
            if b.Close < b.e7:
                flag = True
        if ex is None or ex[0].strftime("%H:%M") != t.exit_time or abs(ex[1] - t.exit) > 1e-6:
            errs.append(f"{t.day} {t.signal} exit {ex} vs {t.exit_time} {t.exit}")
    g = tl.groupby(["day", "window", "side"]).size()
    if len(g) and g.max() > 1:
        errs.append("same side twice in a window")
    if len(tl) and tl.groupby("day").size().max() > 6:
        errs.append("more than 6 trades in a day")
    for (d, grp) in tl.groupby("day"):
        for a, b in zip(grp.itertuples(), list(grp.itertuples())[1:]):
            if b.entry_time < a.exit_time:
                errs.append(f"{d} overlapping trades")
    print(f"Trades checked: {len(tl)}, rule violations: {len(errs)}")
    for e in errs:
        print("  ", e)


if __name__ == "__main__":
    main()

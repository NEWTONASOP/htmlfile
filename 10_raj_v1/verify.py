#!/usr/bin/env python3
"""Independent check of a RAJ v1 run (reads results/<tf>m/, run strategy.py first).

1. Indicators recomputed separately: SMA/EMA/RSI with pandas (ewm/rolling), Supertrend with a
   direct line-by-line transcription of Pine's reference code (nz() semantics included).
2. Signals rebuilt from those values and compared with the strategy's crossover setups.
3. Trades checked against the rules: entry = setup candle close at/after 09:30, range <= 15,
   SL = candle low/high -/+ 0.25, target = 1:3, one trade at a time, max 4 a day, the 3-in-a-row
   stop, exits by 15:15, booked trades never close below cost, P&L arithmetic.

Usage: python 10_raj_v1/verify.py [--timeframe 2|5]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def pine_supertrend(h, l, c, n, factor):
    tr = np.maximum(h - l, np.maximum(abs(h - np.r_[np.nan, c[:-1]]), abs(l - np.r_[np.nan, c[:-1]])))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy().copy()
    atr[: n - 1] = np.nan                                        # ta.atr is na before n bars
    st, dirn = np.full(len(c), np.nan), np.full(len(c), np.nan)
    lower_prev = upper_prev = None                               # lowerBand[1], upperBand[1]
    for i in range(len(c)):
        src = (h[i] + l[i]) / 2
        upper, lower = src + factor * atr[i], src - factor * atr[i]
        plb = 0.0 if lower_prev is None or np.isnan(lower_prev) else lower_prev   # nz()
        pub = 0.0 if upper_prev is None or np.isnan(upper_prev) else upper_prev
        c1 = c[i - 1] if i else np.nan
        lower = lower if (lower > plb or c1 < plb) else plb
        upper = upper if (upper < pub or c1 > pub) else pub
        if i == 0 or np.isnan(atr[i - 1]):
            d = 1
        elif st[i - 1] == pub:
            d = -1 if c[i] > upper else 1
        else:
            d = 1 if c[i] < lower else -1
        dirn[i] = d
        st[i] = lower if d == -1 else upper
        lower_prev, upper_prev = lower, upper
    return st, dirn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", type=int, choices=(2, 5))
    a = ap.parse_args()
    for tf in ([a.timeframe] if a.timeframe else (2, 5)):
        out = HERE / "results" / f"{tf}m"
        b = pd.read_csv(out / "bars_with_indicators.csv", index_col=0)
        b.index = pd.to_datetime(b.index)
        tl = pd.read_csv(out / "trades.csv", parse_dates=["entry_time", "exit_time"])
        for col in ("entry_time", "exit_time"):
            tl[col] = tl[col].dt.tz_localize("Asia/Kolkata")
        title = (out / "summary.txt").read_text().splitlines()[0]
        # settings from the run title, e.g. "SMA 9 x EMA 15, Supertrend 10/3, RSI 21"
        part = title.split("|")[2].strip()
        (t1, n1), (t2, n2) = [(x.split()[0].lower(), int(x.split()[1])) for x in part.split(",")[0].split(" x ")]
        st_n, st_f = part.split("Supertrend ")[1].split(",")[0].split("/")
        rsi_n = int(part.split("RSI ")[1])

        # the CSV holds the backtest window only: indicators need the warm-up, so recompute on it
        # and compare after enough bars for the different seeding to vanish
        c = b.Close
        ma = lambda t, n: c.rolling(n).mean() if t == "sma" else c.ewm(span=n, adjust=False).mean()  # noqa: E731
        m1, m2 = ma(t1, n1), ma(t2, n2)
        ch = c.diff()
        up = ch.clip(lower=0).ewm(alpha=1 / rsi_n, adjust=False).mean()
        dn = (-ch.clip(upper=0)).ewm(alpha=1 / rsi_n, adjust=False).mean()
        r = 100 - 100 / (1 + up / dn)
        st, sd = pine_supertrend(b.High.to_numpy(), b.Low.to_numpy(), c.to_numpy(), int(st_n), float(st_f))
        skip = 300                                                # bars ignored for seeding effects
        cmp = slice(skip, None)
        print(f"== {tf}m  ({len(b)} bars, compared from bar {skip})")
        for name, mine, theirs in (("MA 1", m1, b.ma1), ("MA 2", m2, b.ma2), ("RSI", r, b.rsi),
                                   ("Supertrend", pd.Series(st, b.index), b.supertrend)):
            print(f"  {name:<11} max abs diff {np.nanmax(np.abs((mine - theirs).to_numpy()[cmp])):.6f}")
        print(f"  Supertrend direction mismatches: {(sd[cmp] != b.st_dir.to_numpy()[cmp]).sum()}")

        fast, slow = (m1, m2) if n1 <= n2 else (m2, m1)
        bull = (fast > slow) & (fast.shift() <= slow.shift())
        bear = (fast < slow) & (fast.shift() >= slow.shift())
        ce = bull & (sd == -1) & (r > 60)
        pe = bear & (sd == 1) & (r < 45)
        diff_ce = (ce != b.ce_setup)[skip:].sum()
        diff_pe = (pe != b.pe_setup)[skip:].sum()
        print(f"  setup candles differing: CE {diff_ce}, PE {diff_pe}  (strategy: CE {b.ce_setup[skip:].sum()}, "
              f"PE {b.pe_setup[skip:].sum()})")

        # trade rules
        bar = pd.Timedelta(minutes=tf)
        errs = []
        for k, t in tl.iterrows():
            row = b.loc[t.entry_time]
            ok_setup = row.ce_setup if t.side == "CE" else row.pe_setup
            stop = row.Low - 0.25 if t.side == "CE" else row.High + 0.25
            checks = {
                "setup": ok_setup, "entry=close": abs(t.entry - row.Close) < 0.006,
                "09:30": (t.entry_time + bar).time() >= pd.Timestamp("09:30").time(),
                "range": row.High - row.Low <= 15, "stop": abs(t.stop - stop) < 0.006,
                "1:3": abs(t.target - (t.entry + 3 * (t.entry - t.stop))) < 0.02,
                "15:15": (t.exit_time + bar).time() <= pd.Timestamp("15:15").time()
                and t.exit_time.date() == t.entry_time.date(),
                "no overlap": k == 0 or t.entry_time >= tl.exit_time[k - 1],
            }
            d = 1 if t.side == "CE" else -1
            if isinstance(t.t1_time, str) and t.t1_time != "-":
                checks["cost floor"] = d * (t.exit - t.entry) >= -1e-6 or t.reason.endswith("square-off")
                pts = 0.5 * d * (t.t1_fill - t.entry) + 0.5 * d * (t.exit - t.entry)
            else:
                pts = d * (t.exit - t.entry)
            checks["pnl"] = abs(pts - t.pnl_pts) < 0.006
            errs += [f"{t.entry_time} {n}" for n, v in checks.items() if not v]
        days = tl.groupby(tl.entry_time.dt.date)
        for d0, g in days:
            if len(g) > 4:
                errs.append(f"{d0} more than 4 trades")
            s = np.sign(g.pnl_pts.to_numpy())
            for j in range(3, len(s)):
                if s[j - 1] == s[j - 2] == s[j - 3] != 0:
                    errs.append(f"{d0} trade after 3 in a row")
        print(f"  trades {len(tl)}: rule violations {len(errs)}" + ("".join("\n    " + e for e in errs[:10])))


if __name__ == "__main__":
    main()

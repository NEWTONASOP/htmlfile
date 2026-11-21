#!/usr/bin/env python3
"""
ASHISH SETHI - NIFTY option selling backtest (premiums estimated from NIFTY spot).

Reference Price (RP): NIFTY spot at the start of each trading day (09:15 open). It resets
                      after every successful entry (to the spot at that entry).
Entry   : NIFTY rises 70 points above RP -> sell 1 CE about 200 points above spot.
          NIFTY falls 70 points below RP -> sell 1 PE about 200 points below spot.
          Strike = nearest multiple of 50. Expiry = next weekly expiry (Tuesday; on expiry
          day itself, today's expiry).
Limits  : at most 5 new lots per day and 40 open lots in total. When capacity frees up,
          entries resume (still within the daily limit).
Exits   : each leg on its own: stop loss when its premium rises 30% above its selling price,
          target when it falls 90% below it. Square-off of all open legs on expiry day at the
          close (market closes 15:30; the spec's 15:33 is after the close).
Premium : no option data; each leg's premium is Black-Scholes from NIFTY spot with India VIX
          as volatility (see indicators/black_scholes.py). Prices are on a 0.05 tick.
Data    : NIFTY 50 and India VIX 5-minute candles from Yahoo (about the last 60 days). Inside
          each candle the price path is walked open -> low -> high -> close (rising candle) or
          open -> high -> low -> close (falling candle) in 2-point steps, so stop losses,
          targets and entries happen in a realistic order.

Usage:
    python ashishsethi/strategy.py                 # all available days (~60)
    python ashishsethi/strategy.py --lot 65
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_yf, clean, IST  # noqa: E402
from indicators.black_scholes import bs_price  # noqa: E402
from indicators.expiry import expiry_for, strike_for  # noqa: E402

TRIGGER = 70.0              # points from RP
SL_PCT = 30.0               # premium up 30% -> stop loss
TARGET_PCT = 90.0           # premium down 90% -> target
MAX_NEW_PER_DAY = 5
MAX_OPEN = 40
LOT = 65                    # NIFTY lot size (to be confirmed)
TICK = 0.05
STEP = 2.0                  # path step in NIFTY points inside a candle
BAR = pd.Timedelta(minutes=5)


def tick(x):
    return np.maximum(np.round(np.asarray(x, float) / TICK) * TICK, TICK)


def years_to(expiry: dt.date, t: pd.Timestamp) -> float:
    exp_dt = pd.Timestamp(dt.datetime.combine(expiry, dt.time(15, 30)), tz=IST)
    return max((exp_dt - t).total_seconds(), 0.0) / (365.0 * 24 * 3600)


def bar_path(o, h, lo, c):
    pts = [o, lo, h, c] if c >= o else [o, h, lo, c]
    out = [o]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(abs(b - a) / STEP)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return out


def run(df: pd.DataFrame, a) -> tuple[list[dict], dict]:
    days = sorted(set(df.index.date))
    legs, closed = [], []
    stats = dict(max_open=0, daily_limit_days=0, capacity_blocked=0)
    for day in days:
        d = df[df.index.date == day]
        rp = float(d.Open.iloc[0])
        new_today = 0
        limit_hit = False
        for n_bar, (ts, b) in enumerate(d.iterrows()):
            sigma = float(b.vix) / 100.0
            t_price = ts + BAR / 2
            path = bar_path(float(b.Open), float(b.High), float(b.Low), float(b.Close))
            prev = None
            for p_i, p in enumerate(path):
                opening = p_i == 0
                # 1) exits, each leg on its own
                if legs:
                    K = np.array([l["strike"] for l in legs])
                    T = np.array([years_to(l["expiry"], t_price) for l in legs])
                    call = np.array([l["side"] == "CE" for l in legs])
                    prem = bs_price(p, K, T, sigma, call)
                    keep = []
                    prem = tick(prem)                       # quotes move in 0.05 ticks
                    for l, pr in zip(legs, prem):
                        if pr >= l["sl"]:
                            l.update(exit_time=ts, exit_spot=p, exit=float(tick(pr if opening else l["sl"])),
                                     reason="StopLoss +30%")
                            closed.append(l)
                        elif pr <= l["target"]:
                            l.update(exit_time=ts, exit_spot=p, exit=float(tick(pr if opening else l["target"])),
                                     reason="Target -90%")
                            closed.append(l)
                        else:
                            keep.append(l)
                    legs = keep
                # 2) entries from the reference price
                for side, hit, level in (("CE", p >= rp + TRIGGER, rp + TRIGGER),
                                         ("PE", p <= rp - TRIGGER, rp - TRIGGER)):
                    if not hit:
                        continue
                    if new_today >= MAX_NEW_PER_DAY:
                        limit_hit = True
                        continue
                    if len(legs) >= MAX_OPEN:
                        stats["capacity_blocked"] += 1
                        continue
                    crossed_now = prev is not None and ((prev < level) if side == "CE" else (prev > level))
                    fill_spot = level if crossed_now else p
                    expiry = expiry_for(day, days)
                    K = strike_for(fill_spot, side == "CE")
                    sell = float(tick(bs_price(fill_spot, K, years_to(expiry, t_price), sigma, side == "CE")))
                    legs.append(dict(side=side, entry_time=ts, entry_spot=round(fill_spot, 2), strike=K,
                                     expiry=expiry, sell=sell, sl=sell * (1 + SL_PCT / 100),
                                     target=sell * (1 - TARGET_PCT / 100)))
                    new_today += 1
                    rp = fill_spot                           # RP reset after a successful entry
                stats["max_open"] = max(stats["max_open"], len(legs))
                prev = p
            # 3) expiry-day square-off at the close
            if n_bar == len(d) - 1:
                keep = []
                for l in legs:
                    if l["expiry"] <= day:
                        pr = bs_price(float(b.Close), l["strike"], 0.0, sigma, l["side"] == "CE")
                        l.update(exit_time=ts + BAR, exit_spot=float(b.Close), exit=float(np.round(pr / TICK) * TICK),
                                 reason="Expiry square-off")
                        closed.append(l)
                    else:
                        keep.append(l)
                legs = keep
        stats["daily_limit_days"] += int(limit_hit)
    # legs still open at the end of the data: marked to market
    last_ts, last = df.index[-1], df.iloc[-1]
    for l in legs:
        pr = bs_price(float(last.Close), l["strike"], years_to(l["expiry"], last_ts + BAR), float(last.vix) / 100,
                      l["side"] == "CE")
        l.update(exit_time=last_ts + BAR, exit_spot=float(last.Close), exit=float(tick(pr)),
                 reason="Open (marked to market)")
        closed.append(l)
    return closed, stats


def main():
    global LOT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lot", type=int, default=LOT, help="NIFTY lot size for Rs P&L")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    nifty = clean(fetch_yf("^NSEI", period="60d", interval="5m"))
    vix = clean(fetch_yf("^INDIAVIX", period="60d", interval="5m"))
    df = nifty.join(vix["Close"].rename("vix"), how="left")
    df["vix"] = df["vix"].ffill().bfill()
    sessions = sorted(set(df.index.date))
    if (df.index[-1] + BAR).time() < dt.time(15, 30):
        df = df[df.index.date < sessions[-1]]              # drop an unfinished day
        sessions = sessions[:-1]

    closed, stats = run(df, a)
    tl = pd.DataFrame(closed)
    if tl.empty:
        print("No trades.")
        return
    tl = tl.sort_values("entry_time").reset_index(drop=True)
    tl["pnl_pts"] = (tl.sell - tl.exit).round(2)
    tl["pnl_rs"] = (tl.pnl_pts * a.lot).round(2)
    for col in ("entry_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M")
    tl["expiry"] = tl.expiry.astype(str)

    done = tl[tl.reason != "Open (marked to market)"]
    wins = (done.pnl_pts > 0).sum()
    lines = [
        f"Days              : {len(sessions)}  ({sessions[0]} -> {sessions[-1]})",
        f"Legs sold         : {len(tl)}  (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})",
        f"Closed legs       : {len(done)}  (wins {wins}, losses {len(done) - wins}, "
        f"win rate {100 * wins / max(len(done), 1):.1f}%)",
        f"Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
        f"P&L closed legs   : {done.pnl_pts.sum():+.2f} premium points = Rs {done.pnl_rs.sum():+,.2f} (lot {a.lot})",
        f"P&L incl. open    : {tl.pnl_pts.sum():+.2f} points = Rs {tl.pnl_rs.sum():+,.2f}",
        f"Max open lots     : {stats['max_open']} (limit {MAX_OPEN})",
        f"Days at 5-lot cap : {stats['daily_limit_days']}",
    ]
    header = (f"ASHISH SETHI NIFTY option selling | NIFTY 5m + India VIX | premiums by Black-Scholes\n"
              f"RP = 09:15 open, +/-{TRIGGER:g} pts -> sell CE/PE ~{200} pts OTM (strike step 50), weekly "
              f"expiry (Tue), SL +{SL_PCT:g}%, target -{TARGET_PCT:g}%, max {MAX_NEW_PER_DAY}/day and "
              f"{MAX_OPEN} open, expiry-day square-off.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "legs.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")
    print(header)
    print("\n".join(lines))
    print(f"\nLeg list: {os.path.join(a.out, 'legs.csv')}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Rakesh Rattan - EMA Crossover strategy backtest (5-minute candles, NSE intraday).

EMAs     : 15, 30, 35, 40, 45, 50 and 60 (main) on close. See rakesh/indicators/ema_set.py.
BUY      : the 60 EMA becomes the LOWEST line (all faster EMAs crossed above it).
SELL     : the 60 EMA becomes the HIGHEST line.
Entry    : open of the candle after the crossover candle. Entries 09:15 - 15:00.
Stop loss: BUY 1 tick below the crossover candle's low, SELL 1 tick above its high
           (the crossover candle is the one before the entry candle).
Targets  : at 1:1 book 50% (25 of 50 qty) and move SL to cost; at 1:2 exit the rest.
Other    : one trade at a time; opposite crossovers ignored while in a trade;
           anything open is squared off at 15:15.

Usage:
    python rakesh/strategy.py                       # RELIANCE.NS 5m, last 5 sessions, qty 50
    python rakesh/strategy.py --sessions 40 --cost-pct 0.05
    python rakesh/strategy.py --day 2026-11-13      # print only that day's trades
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, asdict
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root
from common.data import fetch_yf, load_csv, clean  # noqa: E402
from rakesh.indicators import ema_set  # noqa: E402

HERE = Path(__file__).resolve().parent

TICK = 0.10                  # RELIANCE tick size (stocks ₹1,000-5,000)
QTY = 50
ENTRY_LAST_START = time(15, 0)   # entry candle must open before 15:00
SQUARE_OFF = time(15, 15)        # forced exit at the close of the candle ending 15:15
BAR_MIN = 5


# ---------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = pd.concat([df, ema_set.ema_set(df)], axis=1)
    df["warm"] = np.arange(len(df)) >= ema_set.warmup_bars()
    return df


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str                    # BUY / SELL
    signal_time: pd.Timestamp    # crossover candle
    entry_time: pd.Timestamp
    entry: float
    stop: float
    t1: float                    # 1:1
    t2: float                    # 1:2
    t1_time: pd.Timestamp | None = None
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    sl: float = 0.0              # live stop (moves to cost after T1)

    def pnl_pts(self) -> float:
        """Per-share P&L averaged over the full quantity (50% at T1 + 50% at final exit)."""
        d = 1 if self.side == "BUY" else -1
        if self.t1_time is None:
            return d * (self.exit - self.entry)
        return 0.5 * d * (self.t1 - self.entry) + 0.5 * d * (self.exit - self.entry)


def run(df: pd.DataFrame, start_date, tick: float = TICK) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, H, L, C = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    BULL, BEAR, WARM = (df[k].to_numpy() for k in ("bull_cross", "bear_cross", "warm"))
    trades: list[Trade] = []
    pos: Trade | None = None

    for i in range(1, len(df)):
        ts = idx[i]
        end = (ts + pd.Timedelta(minutes=BAR_MIN)).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) entry at this candle's open after a crossover on the previous candle
        j = i - 1
        if (pos is None and dates[j] == dates[i] and dates[i] >= start_date and WARM[j]
                and ts.time() < ENTRY_LAST_START and (BULL[j] or BEAR[j])):
            side = "BUY" if BULL[j] else "SELL"
            px = O[i]
            sl = L[j] - tick if side == "BUY" else H[j] + tick
            r = px - sl if side == "BUY" else sl - px
            if r > 0:   # skip if the open is already beyond the stop
                d = 1 if side == "BUY" else -1
                pos = Trade(side, idx[j], ts, float(px), round(float(sl), 2),
                            float(px + d * r), float(px + 2 * d * r), sl=round(float(sl), 2))

        # 2) manage the open trade on this candle: stop first, then 1:1, then 1:2
        if pos is not None:
            buy = pos.side == "BUY"
            if (L[i] <= pos.sl) if buy else (H[i] >= pos.sl):
                px = min(O[i], pos.sl) if buy else max(O[i], pos.sl)
                pos.reason = "StopLoss" if pos.t1_time is None else "1:1 + cost stop"
                pos.exit_time, pos.exit = ts, float(px)
                trades.append(pos); pos = None
                continue
            if pos.t1_time is None and ((H[i] >= pos.t1) if buy else (L[i] <= pos.t1)):
                pos.t1_time, pos.sl = ts, pos.entry          # book 50%, SL to cost
            if pos.t1_time is not None and ((H[i] >= pos.t2) if buy else (L[i] <= pos.t2)):
                px = max(O[i], pos.t2) if buy else min(O[i], pos.t2)
                pos.reason, pos.exit_time, pos.exit = "1:2 target", ts, float(px)
                trades.append(pos); pos = None
                continue
            # 3) square-off
            if end >= SQUARE_OFF or last_of_day:
                pos.reason = "1:1 + square-off" if pos.t1_time is not None else "Square-off 15:15"
                pos.exit_time, pos.exit = ts, float(C[i])
                trades.append(pos); pos = None
    return trades


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int, cost_pct: float) -> tuple[pd.DataFrame, str]:
    rows = []
    for t in trades:
        d = asdict(t)
        d.pop("sl")
        pts = t.pnl_pts()
        d["pnl_pts"] = round(pts, 2)
        d["pnl_rs"] = round(pts * qty - cost_pct / 100 * t.entry * qty, 2)
        rows.append(d)
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, "No trades in the backtest window."
    for col in ("signal_time", "entry_time", "t1_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    for col in ("entry", "stop", "t1", "t2", "exit"):
        tl[col] = tl[col].round(2)
    wins, losses = tl[tl.pnl_rs > 0], tl[tl.pnl_rs <= 0]
    eq = tl["pnl_rs"].cumsum()
    gw, gl = wins.pnl_rs.sum(), -losses.pnl_rs.sum()
    lines = [
        f"Trades            : {len(tl)}  (BUY {sum(tl.side == 'BUY')}, SELL {sum(tl.side == 'SELL')})",
        f"Winners / Losers  : {len(wins)} / {len(losses)}  (win rate {100 * len(wins) / len(tl):.1f}%)",
        f"Reached 1:1 / 1:2 : {sum(tl.t1_time != '-')} / {sum(tl.reason == '1:2 target')}",
        f"Net P&L (points)  : {tl.pnl_pts.sum():+.2f} per share",
        f"Net P&L (Rs)      : {tl.pnl_rs.sum():+,.2f}  (qty {qty}, cost {cost_pct}% per trade)",
        f"Avg win / loss    : {wins.pnl_rs.mean() if len(wins) else 0:+,.2f} / "
        f"{losses.pnl_rs.mean() if len(losses) else 0:+,.2f} Rs",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        f"Max drawdown (Rs) : {(eq - eq.cummax().clip(lower=0)).min():,.2f}",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
        "",
        "Per day (Rs):",
    ]
    per_day = tl.groupby(tl.entry_time.str[:10]).agg(n=("pnl_rs", "size"), rs=("pnl_rs", "sum"))
    lines += [f"  {d}: {int(r.n):2d} trades  {r.rs:+,.2f}" for d, r in per_day.iterrows()]
    return tl, "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="RELIANCE.NS")
    ap.add_argument("--csv", help="load 5m OHLC from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--tick", type=float, default=TICK, help="tick size for the 1-tick SL buffer")
    ap.add_argument("--qty", type=int, default=QTY, help="total quantity (half booked at 1:1)")
    ap.add_argument("--cost-pct", type=float, default=0.0, help="round-trip cost in %% of entry")
    ap.add_argument("--day", help="print only this date's trades (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    df = clean(load_csv(a.csv) if a.csv else fetch_yf(a.symbol, interval="5m"))
    sessions = sorted(set(df.index.date))
    if not a.include_today and df.index[-1].time() < SQUARE_OFF:
        sessions = sessions[:-1]
        df = df[df.index.date <= sessions[-1]]
    window = sessions[-a.sessions:]
    df = add_indicators(df)
    trades = run(df, window[0], tick=a.tick)
    tl, summary = report(trades, a.qty, a.cost_pct)

    header = (f"Rakesh Rattan EMA crossover | {a.symbol} 5m | {window[0]} -> {window[-1]} "
              f"({len(window)} sessions)\n"
              f"EMAs {'/'.join(map(str, ema_set.FAST_LENGTHS))} vs {ema_set.MAIN_LENGTH}, entry next open "
              f"(before {ENTRY_LAST_START:%H:%M}), SL 1 tick ({a.tick}) beyond crossover candle, "
              f"50% at 1:1 then cost, rest at 1:2, exit by {SQUARE_OFF:%H:%M}.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + summary + "\n")
    df[df.index.date >= window[0]].to_csv(os.path.join(a.out, "bars_with_indicators.csv"))

    print(header)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "signal_time", "entry_time", "entry", "stop", "t1", "t2", "t1_time",
                    "exit_time", "exit", "reason", "pnl_pts", "pnl_rs"]].to_string(index=False))
    print("\n" + summary)


if __name__ == "__main__":
    main()

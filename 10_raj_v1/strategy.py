#!/usr/bin/env python3
"""
RAJ v1 - MA crossover + Supertrend + RSI, NIFTY 50 ATM options (index-point backtest).

Settings (all dashboard-configurable; defaults in brackets):
  timeframe 2m / 5m [both], MA 1 type/period [SMA 9], MA 2 type/period [EMA 15],
  Supertrend ATR length / factor [10 / 3], RSI length [21], lot size [65], lots [1],
  0-day expiry toggle [OFF].

Crossover  : the shorter-period MA (fast) crosses the longer one (slow) on a completed candle
             (ta.crossover / ta.crossunder). Equal periods: MA 1 is the fast line.
CE         : bullish crossover + Supertrend bullish (uptrend) + RSI > 60, all on that candle.
PE         : bearish crossover + Supertrend bearish (downtrend) + RSI < 45, all on that candle.
Entry      : at the close of the crossover candle itself. The candle must close at 09:30 or
             later and before 15:15.
Filter     : skip if the crossover candle's range (High - Low) is more than 15 points.
Stop loss  : CE: crossover candle Low - 0.25 (5 ticks of 0.05). PE: High + 0.25.
Target     : 1:3 (risk = entry - SL). Book 50% there and move the SL to cost.
Trailing   : remaining 50%: every 20 points beyond the 1:3 price moves the SL 10 points
             (target + 20 -> cost + 10, target + 40 -> cost + 20, ...).
Checks     : candle high/low from the candle after entry; SL before target on the same candle.
Position   : one trade at a time; signals while in a trade are ignored.
Day limits : max 4 trades a day; no more entries after 3 profitable or 3 losing trades in a row.
Square-off : 15:15 (close of the last candle before 15:15).
Options    : ATM strike (entry rounded to 50), nearest Tuesday expiry (trading day before if a
             holiday). 0-DTE OFF: on expiry day the next week's expiry is used.
             P&L in NIFTY index points (Yahoo has no option prices).

Usage (from the repository root):
    python 10_raj_v1/strategy.py                         # 2m and 5m, all Yahoo data
    python 10_raj_v1/strategy.py --timeframe 5 --ma1 ema:9 --ma2 sma:21
    python 10_raj_v1/strategy.py --day 2026-11-18        # print one day's trades
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_yf, load_csv, clean, to_timeframe  # noqa: E402
from indicators.moving_averages import moving_average  # noqa: E402
from indicators.supertrend import supertrend, ATR_LENGTH, FACTOR  # noqa: E402
from indicators.rsi import rsi, LENGTH as RSI_LENGTH, BULL_ABOVE, BEAR_BELOW  # noqa: E402

SYMBOL = "^NSEI"
TIMEFRAMES = (2, 5)
MA1 = ("sma", 9)
MA2 = ("ema", 15)
MAX_RANGE = 15.0                 # skip crossover candles with High - Low > 15 points
SL_BUFFER = 0.25                 # 5 ticks x 0.05
RR = 3.0                         # target = 1:3
BOOK_FRACTION = 0.5              # 50% booked at 1:3
TRAIL_STEP = 20.0                # every 20 points beyond the 1:3 price ...
TRAIL_MOVE = 10.0                # ... moves the SL 10 points
FIRST_ENTRY_CLOSE = time(9, 30)  # entry candle must close at 09:30 or later
SQUARE_OFF = time(15, 15)
MAX_TRADES_DAY = 4
MAX_STREAK = 3
LOT_SIZE = 65
STRIKE_STEP = 50
EXPIRY_WEEKDAY = 1               # Tuesday


# ---------------------------------------------------------------- options
def option_for(spot: float, day: date, trading_days: set[date], last_day: date, zero_dte: bool):
    atm = int(math.floor(spot / STRIKE_STEP + 0.5) * STRIKE_STEP)

    def shifted(tue: date) -> date:
        if tue <= last_day and tue not in trading_days:          # holiday -> trading day before
            return max(x for x in trading_days if x < tue)
        return tue

    tue = day + timedelta(days=(EXPIRY_WEEKDAY - day.weekday()) % 7)
    exp = shifted(tue)
    if exp < day or (exp == day and not zero_dte):
        exp = shifted(tue + timedelta(days=7))
    return atm, exp


# ---------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame, ma1, ma2, st_len, st_factor, rsi_len) -> pd.DataFrame:
    df = df.copy()
    m1, m2 = moving_average(df, *ma1), moving_average(df, *ma2)
    fast, slow = (m1, m2) if ma1[1] <= ma2[1] else (m2, m1)
    df["ma1"], df["ma2"], df["fast"], df["slow"] = m1, m2, fast, slow
    df = df.join(supertrend(df, st_len, st_factor))
    df["rsi"] = rsi(df, rsi_len)
    pf, ps = fast.shift(1), slow.shift(1)
    df["bull_cross"] = (fast > slow) & (pf <= ps)               # ta.crossover (na -> False)
    df["bear_cross"] = (fast < slow) & (pf >= ps)               # ta.crossunder
    df["ce_setup"] = df.bull_cross & (df.st_dir == -1) & (df.rsi > BULL_ABOVE)
    df["pe_setup"] = df.bear_cross & (df.st_dir == 1) & (df.rsi < BEAR_BELOW)
    return df


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str                     # CE / PE
    entry_time: pd.Timestamp      # crossover candle (filled at its close)
    entry: float                  # NIFTY index
    stop: float                   # initial SL
    target: float                 # 1:3
    strike: int
    expiry: date
    sl: float = 0.0               # current SL
    best: float = 0.0             # best price after the 1:3 booking
    t1_time: pd.Timestamp | None = None
    t1_fill: float | None = None
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    sl_path: list = field(default_factory=list)                # (time, SL) every time it moves

    @property
    def d(self) -> int:
        return 1 if self.side == "CE" else -1

    @property
    def pnl_pts(self) -> float:
        """Points per unit, averaged over the full quantity."""
        rest = self.d * (self.exit - self.entry)
        if self.t1_fill is None:
            return rest
        return BOOK_FRACTION * self.d * (self.t1_fill - self.entry) + (1 - BOOK_FRACTION) * rest


def run(df: pd.DataFrame, start_date, minutes: int, zero_dte: bool):
    idx, dates = df.index, df.index.date
    O, H, L, C, RNG = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close", "range"))
    CE, PE = df["ce_setup"].to_numpy(), df["pe_setup"].to_numpy()
    bar = pd.Timedelta(minutes=minutes)
    trading_days, last_day = set(dates), dates[-1]
    trades: list[Trade] = []
    signals = []                    # every candle with all 3 conditions, and what happened
    pos: Trade | None = None
    day, n_day, streak = None, 0, 0     # streak: +k = k wins in a row, -k = k losses

    def close(i, px, reason):
        nonlocal pos, streak
        pos.exit_time, pos.exit, pos.reason = idx[i], float(px), reason
        trades.append(pos)
        p = pos.pnl_pts
        streak = (max(streak, 0) + 1) if p > 0 else (min(streak, 0) - 1) if p < 0 else 0
        pos = None

    for i in range(len(df)):
        ts = idx[i]
        if dates[i] != day:
            day, n_day, streak = dates[i], 0, 0
        end = (ts + bar).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) manage the open trade on this candle: SL first, then 1:3, then trail, square-off
        if pos is not None:
            ce = pos.side == "CE"
            if (L[i] <= pos.sl) if ce else (H[i] >= pos.sl):
                px = min(O[i], pos.sl) if ce else max(O[i], pos.sl)
                reason = ("StopLoss" if pos.t1_time is None else
                          "1:3 + cost SL" if pos.sl == pos.entry else "1:3 + trailing SL")
                close(i, px, reason)
            else:
                if pos.t1_time is None and ((H[i] >= pos.target) if ce else (L[i] <= pos.target)):
                    pos.t1_time = ts
                    pos.t1_fill = float(max(O[i], pos.target) if ce else min(O[i], pos.target))
                    pos.sl, pos.best = pos.entry, pos.target
                    pos.sl_path.append((ts, pos.sl))
                if pos.t1_time is not None:
                    pos.best = max(pos.best, H[i]) if ce else min(pos.best, L[i])
                    steps = math.floor(round(pos.d * (pos.best - pos.target), 6) / TRAIL_STEP)
                    new_sl = pos.entry + pos.d * TRAIL_MOVE * max(steps, 0)
                    if pos.d * (new_sl - pos.sl) > 0:
                        pos.sl = new_sl
                        pos.sl_path.append((ts, pos.sl))
                if end >= SQUARE_OFF or last_of_day:
                    close(i, C[i], "Square-off 15:15" if pos.t1_time is None else "1:3 + square-off")

        # 2) signal on this candle's close -> enter at that close
        if dates[i] < start_date or not (CE[i] or PE[i]):
            continue
        side = "CE" if CE[i] else "PE"
        status = "taken"
        if (ts + bar).time() < FIRST_ENTRY_CLOSE:
            status = "before 09:30"
        elif end >= SQUARE_OFF or last_of_day:
            status = "at square-off"
        elif RNG[i] > MAX_RANGE:
            status = "range > 15"
        elif pos is not None:
            status = "in trade"
        elif n_day >= MAX_TRADES_DAY:
            status = "4 trades done"
        elif abs(streak) >= MAX_STREAK:
            status = "3 in a row stop"
        signals.append((ts, side, status))
        if status != "taken":
            continue
        entry = float(C[i])
        stop = L[i] - SL_BUFFER if side == "CE" else H[i] + SL_BUFFER
        target = entry + RR * (entry - stop)                       # CE above, PE below
        strike, exp = option_for(entry, dates[i], trading_days, last_day, zero_dte)
        pos = Trade(side, ts, entry, round(float(stop), 2), round(float(target), 2), strike, exp)
        pos.sl = pos.stop
        pos.sl_path.append((ts, pos.sl))
        n_day += 1

    sig = pd.DataFrame(signals, columns=["candle", "side", "status"])
    return trades, sig


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int):
    rows = []
    for t in trades:
        rows.append(dict(side=t.side, entry_time=t.entry_time, entry=t.entry, stop=t.stop,
                         target=t.target, strike=t.strike, expiry=t.expiry, t1_time=t.t1_time,
                         t1_fill=t.t1_fill, final_sl=t.sl, exit_time=t.exit_time, exit=t.exit,
                         reason=t.reason, pnl_pts=round(t.pnl_pts, 2),
                         pnl_rs=round(t.pnl_pts * qty, 2),
                         sl_path=" > ".join(f"{a:%H:%M} {b:.2f}" for a, b in t.sl_path)))
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, ["No trades in the backtest window."]
    for col in ("entry_time", "t1_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    for col in ("entry", "t1_fill", "final_sl", "exit"):
        tl[col] = pd.to_numeric(tl[col]).round(2)
    wins, losses = tl[tl.pnl_pts > 0], tl[tl.pnl_pts < 0]
    eq = tl.pnl_rs.cumsum()
    gw, gl = wins.pnl_rs.sum(), -losses.pnl_rs.sum()
    lines = [
        f"Trades            : {len(tl)}  (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})",
        f"Winners / losers  : {len(wins)} / {len(losses)}  (win rate {100 * len(wins) / len(tl):.1f}%)",
        f"Reached 1:3       : {sum(tl.t1_time != '-')}",
        f"Net P&L           : {tl.pnl_pts.sum():+.2f} NIFTY points per unit = Rs {tl.pnl_rs.sum():+,.2f} (qty {qty})",
        f"Avg win / loss    : {wins.pnl_pts.mean() if len(wins) else 0:+.2f} / "
        f"{losses.pnl_pts.mean() if len(losses) else 0:+.2f} points",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        f"Max drawdown      : Rs {(eq - eq.cummax().clip(lower=0)).min():,.2f}",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    return tl, lines


def parse_ma(s: str):
    t, n = s.lower().split(":")
    return t, int(n)


def run_timeframe(minutes: int, a) -> None:
    raw = load_csv(a.csv) if a.csv else fetch_yf(a.symbol, minutes)
    df = to_timeframe(clean(raw), minutes)
    bar = pd.Timedelta(minutes=minutes)
    sessions = sorted(set(df.index.date))
    if not a.include_today and (df.index[-1] + bar).time() < SQUARE_OFF:
        sessions = sessions[:-1]                                  # session not finished
        df = df[df.index.date <= sessions[-1]]
    df = add_indicators(df, a.ma1, a.ma2, a.st_atr, a.st_factor, a.rsi_len)
    df["range"] = df.High - df.Low
    window = sessions[1:]                                         # first session: warm-up
    if a.sessions:
        window = window[-a.sessions:]
    trades, sig = run(df, window[0], minutes, a.zero_dte)
    qty = a.lot_size * a.lots
    tl, lines = report(trades, qty)

    out = os.path.join(a.out, f"{minutes}m")
    os.makedirs(out, exist_ok=True)
    src = a.csv if a.csv else f"{a.symbol} (yfinance)"
    title = (f"RAJ v1 | {src} {minutes}m | {a.ma1[0].upper()} {a.ma1[1]} x {a.ma2[0].upper()} {a.ma2[1]}, "
             f"Supertrend {a.st_atr}/{a.st_factor:g}, RSI {a.rsi_len} | {window[0]} -> {window[-1]} "
             f"({len(window)} sessions)")
    counts = sig.status.value_counts()
    sig_line = "Signals (all 3 conditions): " + ", ".join(f"{k}={v}" for k, v in counts.items())
    tl.to_csv(os.path.join(out, "trades.csv"), index=False)
    sig.to_csv(os.path.join(out, "signals.csv"), index=False)
    view = df[df.index.date >= window[0]]
    view.to_csv(os.path.join(out, "bars_with_indicators.csv"))
    with open(os.path.join(out, "summary.txt"), "w") as f:
        f.write(title + "\n\n" + "\n".join(lines) + "\n" + sig_line + "\n")

    print(title)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "entry_time", "entry", "stop", "target", "strike", "expiry", "t1_time",
                    "exit_time", "exit", "reason", "pnl_pts"]].to_string(index=False))
    print("\n" + "\n".join(lines) + "\n" + sig_line + f"\nOutput: {out}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframe", type=int, choices=TIMEFRAMES, help="2 or 5 minutes (default: both)")
    ap.add_argument("--ma1", type=parse_ma, default=MA1, help="MA 1 as type:period, e.g. sma:9")
    ap.add_argument("--ma2", type=parse_ma, default=MA2, help="MA 2 as type:period, e.g. ema:15")
    ap.add_argument("--st-atr", type=int, default=ATR_LENGTH, help="Supertrend ATR length")
    ap.add_argument("--st-factor", type=float, default=FACTOR, help="Supertrend factor")
    ap.add_argument("--rsi-len", type=int, default=RSI_LENGTH)
    ap.add_argument("--lot-size", type=int, default=LOT_SIZE)
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--zero-dte", action="store_true", help="trade the expiring contract on expiry day")
    ap.add_argument("--symbol", default=SYMBOL, help="Yahoo symbol (default ^NSEI; others only to test the backtest)")
    ap.add_argument("--csv", help="NIFTY candles from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, help="last N sessions only (default: all data)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--day", help="print only trades entered on this date (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()
    for tf in ([a.timeframe] if a.timeframe else TIMEFRAMES):
        run_timeframe(tf, a)


if __name__ == "__main__":
    main()

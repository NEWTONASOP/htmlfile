#!/usr/bin/env python3
"""
OD SOFTWARE - DEMA 20 / SMA 40 arrow strategy backtest (NIFTY 3-minute, NSE intraday).

Signal     : the BUY / SELL arrows of the closed-source "Od trading software no wm" script,
             decoded: BUY arrow  = DEMA 20 (close) crosses above SMA 40 (close),
                      SELL arrow = DEMA 20 crosses below SMA 40.
Entry      : open of the candle after the arrow candle closes.
Reversal   : an opposite arrow exits the open trade and enters the other side at that open.
Stop loss  : 1% from entry.
Trailing   : once price reaches +1% (target, 1:1), the stop moves to entry (breakeven) and
             then trails 1% behind the best price reached (high for BUY, low for SELL).
             A trade ends on whichever comes first: SL, trailing SL, opposite arrow, 15:15.
Session    : intraday; entries on candles opening before 15:00, everything squared off at
             15:15 (close of the 15:12 candle). Nothing is carried overnight.
Fills      : a candle that touches the stop and the target counts the stop first. A stop
             moved by this candle's high/low is used from the next candle. A gap through the
             stop fills at the candle's open.
Output     : results/trades.csv, results/summary.txt, results/bars_with_indicators.csv.

Usage (from the repository root):
    python odsoftware/strategy.py                       # ^NSEI from yfinance, last 20 sessions
    python odsoftware/strategy.py --csv odsoftware/data/NSE_NIFTY_3.csv --sessions 40
    python odsoftware/strategy.py --qty 65 --cost-pct 0.02
    python odsoftware/strategy.py --day 2026-11-17
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_1m, load_csv, clean, to_timeframe  # noqa: E402
from indicators import dema as dema_ind, sma as sma_ind  # noqa: E402

TIMEFRAME_MIN = 3
SL_PCT = 1.0                     # initial stop, % from entry
TARGET_PCT = 1.0                 # profit that switches the trailing stop on (1:1)
TRAIL_PCT = 1.0                  # trailing distance behind the best price, %
ENTRY_CUTOFF = time(15, 0)       # an entry candle must open before 15:00
SQUARE_OFF = time(15, 15)        # close of the candle ending 15:15
QTY = 65                         # NIFTY lot size
COST_PCT = 0.0                   # round-trip costs, % of entry value


# ---------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    f, s = dema_ind.dema(df), sma_ind.sma(df)
    df[f.name], df[s.name] = f, s
    # ta.crossover / ta.crossunder on completed candles = the script's BUY / SELL arrows
    df["buy_arrow"] = (f > s) & (f.shift(1) <= s.shift(1))
    df["sell_arrow"] = (f < s) & (f.shift(1) >= s.shift(1))
    # DEMA = EMA of an EMA: wait 3 x 40 candles so both lines have settled
    df["warm"] = np.arange(len(df)) >= 3 * sma_ind.LENGTH
    return df


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str                    # BUY / SELL
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    initial_stop: float
    target: float
    stop: float                  # current stop (moves after the target)
    best: float                  # best price reached since entry
    target_hit: bool = False
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pts(self) -> float:
        return (self.exit - self.entry) if self.side == "BUY" else (self.entry - self.exit)


def run(df: pd.DataFrame, start_date) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, H, L, C = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    BA, SA, WARM = (df[k].to_numpy() for k in ("buy_arrow", "sell_arrow", "warm"))
    bar = pd.Timedelta(minutes=TIMEFRAME_MIN)
    sl, tg, tr = SL_PCT / 100, TARGET_PCT / 100, TRAIL_PCT / 100
    trades: list[Trade] = []
    pos: Trade | None = None
    pending = None

    def close(ts, px, reason):
        nonlocal pos
        pos.exit_time, pos.exit, pos.reason = ts, float(px), reason
        trades.append(pos)
        pos = None

    def stop_reason(t: Trade) -> str:
        if not t.target_hit:
            return "StopLoss 1%"
        return "Breakeven SL" if t.stop == t.entry else "Trailing SL"

    for i in range(1, len(df)):
        ts = idx[i]
        end = (ts + bar).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) act on the previous candle's arrow at this candle's open (same day only)
        if pending is not None and dates[i - 1] == dates[i]:
            if pending["exit"] and pos is not None:
                close(ts, O[i], "Opposite arrow")
            if pos is None and ts.time() < ENTRY_CUTOFF:
                side, e = pending["enter"], float(O[i])
                if side == "BUY":
                    stop, target = e * (1 - sl), e * (1 + tg)
                else:
                    stop, target = e * (1 + sl), e * (1 - tg)
                pos = Trade(side, pending["signal_time"], ts, e, stop, target, stop, e)
        pending = None

        # 2) stop (initial or trailing) inside the candle, with the level set before it
        if pos is not None:
            if pos.side == "BUY" and L[i] <= pos.stop:
                close(ts, min(O[i], pos.stop), stop_reason(pos))
            elif pos.side == "SELL" and H[i] >= pos.stop:
                close(ts, max(O[i], pos.stop), stop_reason(pos))

        # 3) target -> breakeven, then trail 1% behind the best price (used from next candle)
        if pos is not None:
            if pos.side == "BUY":
                pos.best = max(pos.best, H[i])
                if pos.best >= pos.target:
                    pos.target_hit = True
                    pos.stop = max(pos.stop, pos.entry, pos.best * (1 - tr))
            else:
                pos.best = min(pos.best, L[i])
                if pos.best <= pos.target:
                    pos.target_hit = True
                    pos.stop = min(pos.stop, pos.entry, pos.best * (1 + tr))

        # 4) intraday square-off
        if pos is not None and (end >= SQUARE_OFF or last_of_day):
            close(ts, C[i], "Square-off 15:15")

        # 5) arrow on this completed candle -> act at the next open
        if dates[i] < start_date or not WARM[i] or end >= SQUARE_OFF or last_of_day:
            continue
        arrow = "BUY" if BA[i] else "SELL" if SA[i] else None
        if arrow is None:
            continue
        if pos is not None and pos.side != arrow:
            pending = dict(exit=True, enter=arrow, signal_time=ts)      # reversal
        elif pos is None:
            pending = dict(exit=False, enter=arrow, signal_time=ts)     # fresh entry

    return trades


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int, cost_pct: float):
    rows = []
    for t in trades:
        d = asdict(t)
        cost = cost_pct / 100 * t.entry * qty
        d["pnl_pts"] = round(t.pnl_pts, 2)
        d["gross_rs"] = round(t.pnl_pts * qty, 2)
        d["cost_rs"] = round(cost, 2)
        d["net_rs"] = round(t.pnl_pts * qty - cost, 2)
        rows.append(d)
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, ["No trades in the backtest window."]
    for col in ("signal_time", "entry_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M")
    for col in ("entry", "initial_stop", "target", "stop", "best", "exit"):
        tl[col] = tl[col].round(2)
    wins, losses = tl[tl.net_rs > 0], tl[tl.net_rs <= 0]
    eq = tl.net_rs.cumsum()
    gw, gl = wins.net_rs.sum(), -losses.net_rs.sum()
    lines = [
        f"Total trades      : {len(tl)}  (BUY {sum(tl.side == 'BUY')}, SELL {sum(tl.side == 'SELL')})",
        f"Winning / losing  : {len(wins)} / {len(losses)}",
        f"Win rate          : {100 * len(wins) / len(tl):.1f}%",
        f"Reached +1%       : {int(tl.target_hit.sum())} trades (trailing switched on)",
        f"Gross P&L         : {tl.pnl_pts.sum():+.2f} points = Rs {tl.gross_rs.sum():+,.2f} (qty {qty})",
        f"Costs             : Rs {tl.cost_rs.sum():,.2f} ({cost_pct}% round trip)",
        f"Net P&L           : Rs {tl.net_rs.sum():+,.2f}",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        f"Max drawdown      : Rs {(eq - eq.cummax().clip(lower=0)).min():,.2f}",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    return tl, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="^NSEI", help="yfinance symbol (default ^NSEI = NIFTY 50)")
    ap.add_argument("--csv", help="load candles from CSV instead of yfinance (e.g. the TradingView export)")
    ap.add_argument("--sessions", type=int, default=20,
                    help="trading sessions to backtest (yfinance: max ~20; TradingView CSV: ~40)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--qty", type=int, default=QTY)
    ap.add_argument("--cost-pct", type=float, default=COST_PCT, help="round-trip cost, %% of entry value")
    ap.add_argument("--day", help="print only this date's trades (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    raw = load_csv(a.csv) if a.csv else fetch_1m(a.symbol, days=30)
    df = to_timeframe(clean(raw), TIMEFRAME_MIN)
    sessions = sorted(set(df.index.date))
    bar = pd.Timedelta(minutes=TIMEFRAME_MIN)
    if not a.include_today and (df.index[-1] + bar).time() < SQUARE_OFF:   # session not finished
        sessions = sessions[:-1]
        df = df[df.index.date <= sessions[-1]]
    df = add_indicators(df)
    warm_from = df.index[df["warm"]][0].date()
    window = [d for d in sessions if d >= warm_from][-a.sessions:]
    trades = run(df, window[0])
    tl, lines = report(trades, a.qty, a.cost_pct)

    src = a.csv if a.csv else f"{a.symbol} (yfinance 1m -> 3m)"
    title = (f"OD SOFTWARE DEMA {dema_ind.LENGTH} / SMA {sma_ind.LENGTH} arrows | {src} | "
             f"{TIMEFRAME_MIN}m | {window[0]} -> {window[-1]} ({len(window)} sessions)")
    header = (f"{title}\nEntry next open after an arrow, reverse on the opposite arrow, SL {SL_PCT}%, "
              f"at +{TARGET_PCT}% stop to breakeven then trail {TRAIL_PCT}% behind the best price, "
              f"entries until {ENTRY_CUTOFF:%H:%M}, exit by {SQUARE_OFF:%H:%M}.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")
    df[df.index.date >= window[0]].to_csv(os.path.join(a.out, "bars_with_indicators.csv"))

    print(header)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "signal_time", "entry_time", "entry", "exit_time", "exit",
                    "reason", "pnl_pts", "net_rs"]].to_string(index=False))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

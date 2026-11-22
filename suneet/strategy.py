#!/usr/bin/env python3
"""
SUNEET - Williams Fractal 7 strategy backtest (NIFTY index, 3-minute candles).

Indicator  : TradingView built-in Williams fractal, Periods 7 (indicators/williams_fractal.py).
CE (BUY)   : red arrow below a candle (down fractal, swing low).
PE (SELL)  : green arrow above a candle (up fractal, swing high).
Signal     : when the arrow appears live: the arrow on candle X is confirmed when candle X+7
             closes (21 minutes later on 3m); TradingView then draws it back on candle X.
Entry      : open of the candle after the confirming candle (X+8).
Stop loss  : the arrow candle's (X) low (CE) / high (PE), wick, checked on every candle.
Exit       : the next opposite arrow exits and reverses at the next open; one position at a
             time. A same-side arrow while in a trade is ignored. After a stop, the next arrow
             of either side opens a new trade.
Session    : entries on candles opening before 15:00; everything squared off at 15:15 (close
             of the 15:12 candle). Arrows are not carried to the next day.
Options    : P&L in NIFTY index points (Yahoo has no option prices). Each trade lists the
             option it stands for: ATM = entry price rounded to 50; CE strike = ATM - 50
             (50 points ITM), PE strike = ATM + 100 (100 points ITM); nearest weekly expiry
             (Tuesday, or the trading day before if Tuesday is a holiday); on expiry day itself,
             next week's expiry.
Output     : results/trades.csv, results/summary.txt, results/bars_with_indicators.csv.

Usage (from the repository root):
    python suneet/strategy.py                      # ^NSEI 3m from yfinance, last 20 sessions
    python suneet/strategy.py --sessions 5
    python suneet/strategy.py --day 2026-11-18
    python suneet/strategy.py --csv nifty_3m.csv   # Datetime,Open,High,Low,Close (IST)
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, asdict
from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_1m, load_csv, clean, to_timeframe  # noqa: E402
from indicators.williams_fractal import williams_fractal, PERIODS  # noqa: E402

SYMBOL = "^NSEI"
TIMEFRAME_MIN = 3
ENTRY_CUTOFF = time(15, 0)       # an entry candle must open before 15:00
SQUARE_OFF = time(15, 15)        # close of the candle ending 15:15
QTY = 65                         # NIFTY lot size
COST_PCT = 0.0                   # round-trip costs, % of entry value
STRIKE_STEP = 50
CE_ITM = 50                      # CE strike = ATM - 50
PE_ITM = 100                     # PE strike = ATM + 100
EXPIRY_WEEKDAY = 1               # Tuesday


# ---------------------------------------------------------------- options
def option_for(side: str, spot: float, day: date, trading_days: set[date], last_day: date):
    """Strike and expiry the trade stands for."""
    atm = math.floor(spot / STRIKE_STEP + 0.5) * STRIKE_STEP
    strike = atm - CE_ITM if side == "CE" else atm + PE_ITM

    def shifted(tue: date) -> date:
        if tue <= last_day and tue not in trading_days:          # holiday -> trading day before
            return max(x for x in trading_days if x < tue)
        return tue                                               # (after the data: assume no holiday)

    tue = day + timedelta(days=(EXPIRY_WEEKDAY - day.weekday()) % 7)   # this week's Tuesday
    exp = shifted(tue)
    if exp <= day:                                               # expiry day itself -> next week
        exp = shifted(tue + timedelta(days=7))
    return strike, exp


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str                    # CE / PE
    arrow_time: pd.Timestamp     # candle the arrow is drawn on (stop-loss candle)
    signal_time: pd.Timestamp    # candle on whose close the arrow appears (arrow + 7 candles)
    entry_time: pd.Timestamp
    entry: float                 # NIFTY index
    stop: float                  # arrow candle low (CE) / high (PE)
    strike: int = 0
    expiry: date | None = None
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pts(self) -> float:
        return (self.exit - self.entry) if self.side == "CE" else (self.entry - self.exit)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Arrows on their candle, and the same arrows on the candle where they become known."""
    df = df.join(williams_fractal(df, PERIODS))
    df["ce_signal"] = df["down_arrow"].shift(PERIODS, fill_value=False)   # red arrow appears
    df["pe_signal"] = df["up_arrow"].shift(PERIODS, fill_value=False)     # green arrow appears
    df["arrow_low"] = df["Low"].shift(PERIODS)                            # CE stop: arrow candle low
    df["arrow_high"] = df["High"].shift(PERIODS)                          # PE stop: arrow candle high
    return df


def run(df: pd.DataFrame, start_date) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, H, L, C = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    UP, DOWN = df["pe_signal"].to_numpy(), df["ce_signal"].to_numpy()
    ALOW, AHIGH = df["arrow_low"].to_numpy(), df["arrow_high"].to_numpy()
    bar = pd.Timedelta(minutes=TIMEFRAME_MIN)
    trading_days, last_day = set(dates), dates[-1]
    trades: list[Trade] = []
    pos: Trade | None = None
    pending = None

    def close(ts, px, reason):
        nonlocal pos
        pos.exit_time, pos.exit, pos.reason = ts, float(px), reason
        trades.append(pos)
        pos = None

    for i in range(len(df)):
        ts = idx[i]
        end = (ts + bar).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) act on the previous candle's arrow at this candle's open (same day only)
        if pending is not None and i > 0 and dates[i - 1] == dates[i]:
            side, sig_i = pending
            if pos is not None and pos.side != side:
                close(ts, O[i], "Opposite arrow")
            if pos is None and ts.time() < ENTRY_CUTOFF:
                stop = ALOW[sig_i] if side == "CE" else AHIGH[sig_i]
                strike, exp = option_for(side, O[i], dates[i], trading_days, last_day)
                pos = Trade(side, idx[sig_i - PERIODS], idx[sig_i], ts, float(O[i]), float(stop), strike, exp)
        pending = None

        # 2) stop loss inside the candle (wick)
        if pos is not None:
            if pos.side == "CE" and L[i] <= pos.stop:
                close(ts, min(O[i], pos.stop), "StopLoss")
            elif pos.side == "PE" and H[i] >= pos.stop:
                close(ts, max(O[i], pos.stop), "StopLoss")

        # 3) intraday square-off
        if pos is not None and (end >= SQUARE_OFF or last_of_day):
            close(ts, C[i], "Square-off 15:15")

        # 4) arrow that appears on this candle's close -> act at the next open
        if dates[i] < start_date or end >= SQUARE_OFF or last_of_day:
            continue
        if DOWN[i] and UP[i]:
            continue                                   # both arrows on one candle: no signal
        side = "CE" if DOWN[i] else "PE" if UP[i] else None
        if side is not None and (pos is None or pos.side != side):
            pending = (side, i)

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
    for col in ("arrow_time", "signal_time", "entry_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M")
    for col in ("entry", "stop", "exit"):
        tl[col] = tl[col].round(2)
    wins, losses = tl[tl.net_rs > 0], tl[tl.net_rs <= 0]
    eq = tl.net_rs.cumsum()
    gw, gl = wins.net_rs.sum(), -losses.net_rs.sum()
    lines = [
        f"Total trades      : {len(tl)}  (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})",
        f"Winning / losing  : {len(wins)} / {len(losses)}",
        f"Win rate          : {100 * len(wins) / len(tl):.1f}%",
        f"Gross P&L         : {tl.pnl_pts.sum():+.2f} NIFTY points = Rs {tl.gross_rs.sum():+,.2f} (qty {qty})",
        f"Costs             : Rs {tl.cost_rs.sum():,.2f} ({cost_pct}% round trip)",
        f"Net P&L           : Rs {tl.net_rs.sum():+,.2f}",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        f"Max drawdown      : Rs {(eq - eq.cummax().clip(lower=0)).min():,.2f}",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    return tl, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="load NIFTY candles from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=20, help="trading sessions to backtest (yfinance: max ~20)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--qty", type=int, default=QTY)
    ap.add_argument("--cost-pct", type=float, default=COST_PCT, help="round-trip cost, %% of entry value")
    ap.add_argument("--day", help="print only trades entered on this date (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    raw = load_csv(a.csv) if a.csv else fetch_1m(SYMBOL, days=30)
    df = to_timeframe(clean(raw), TIMEFRAME_MIN)
    sessions = sorted(set(df.index.date))
    bar = pd.Timedelta(minutes=TIMEFRAME_MIN)
    if not a.include_today and (df.index[-1] + bar).time() < SQUARE_OFF:
        sessions = sessions[:-1]                                   # session not finished
        df = df[df.index.date <= sessions[-1]]
    df = add_indicators(df)
    window = sessions[1:][-a.sessions:]                            # first session: fractal warm-up
    trades = run(df, window[0])
    tl, lines = report(trades, a.qty, a.cost_pct)

    src = a.csv if a.csv else f"{SYMBOL} (yfinance 1m -> 3m)"
    title = (f"SUNEET Williams Fractal {PERIODS} | {src} | {TIMEFRAME_MIN}m | "
             f"{window[0]} -> {window[-1]} ({len(window)} sessions)")
    header = (f"{title}\nCE on red arrow / PE on green arrow when the arrow appears ({PERIODS} candles after "
              f"its candle), entry next open, SL arrow candle wick, exit + reverse on the opposite arrow, entries until "
              f"{ENTRY_CUTOFF:%H:%M}, exit by {SQUARE_OFF:%H:%M}. P&L in NIFTY index points.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")
    df[df.index.date >= window[0]].to_csv(os.path.join(a.out, "bars_with_indicators.csv"))

    print(header)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "arrow_time", "signal_time", "entry_time", "entry", "stop", "strike", "expiry",
                    "exit_time", "exit", "reason", "pnl_pts"]].to_string(index=False))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

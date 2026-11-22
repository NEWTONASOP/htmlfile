#!/usr/bin/env python3
"""
OD SOFTWARE - the script's own trades + 1% stop and trailing after target (3-minute, NSE).

Signal     : the script's trade signal, decoded: EMA 4 of close crossing an ATR trailing stop
             (1.7 x ATR 7). BUY = EMA crosses above the trail, SELL = crosses below. The
             signals always alternate, so every signal opens a trade: entries are the same as
             the script's Strategy Tester on TradingView.
Entry      : open of the candle after the signal candle.
Reversal   : the opposite signal exits the open trade and enters the other side at that open.
Stop loss  : whichever is closer to entry: 10 points (the script's stop) or 1%.
Target     : at +20 points (the script's target) the trade is NOT booked: the stop moves to
             entry (breakeven) and then trails 1% behind the best price (high for BUY, low for
             SELL). It only tightens.
Session    : none, like the script: trades are held overnight; a trade still open at the end
             of the data is closed at the last close ("Open at end").
Fills      : stops and target tracking start on the candle after entry (as the script's exit
             orders). A stop moved by a candle's high/low is used from the next candle; a
             candle touching the stop exits at the stop, or at the open if it gapped through.
Output     : results/trades.csv, results/summary.txt, results/bars_with_indicators.csv.

Usage (from the repository root):
    python odsoftware/strategy.py                       # ^NSEI from yfinance, last 20 sessions
    python odsoftware/strategy.py --csv odsoftware/data/NSE_NIFTY_3.csv --sessions 60
    python odsoftware/strategy.py --symbol RELIANCE.NS --qty 100
    python odsoftware/strategy.py --day 2026-11-17
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_1m, load_csv, clean, to_timeframe  # noqa: E402
from indicators import dema as dema_ind, sma as sma_ind  # noqa: E402
from indicators.atr_trail import atr_trail  # noqa: E402

TIMEFRAME_MIN = 3
SL_POINTS = 10.0                 # the script's stop ("Point" mode)
TARGET_POINTS = 20.0             # the script's target: here it switches the trailing stop on
SL_PCT = 1.0                     # extra stop: the closer of SL_POINTS and SL_PCT is used
TRAIL_PCT = 1.0                  # trailing distance behind the best price after the target
QTY = 65                         # NIFTY lot size; set --qty for stocks
COST_PCT = 0.0                   # round-trip costs, % of entry value


# ---------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # chart lines and arrows of the script (display; checked by verify.py)
    f, s = dema_ind.dema(df), sma_ind.sma(df)
    df[f.name], df[s.name] = f, s
    df["buy_arrow"] = (f > s) & (f.shift(1) <= s.shift(1))
    df["sell_arrow"] = (f < s) & (f.shift(1) >= s.shift(1))
    # trade signal
    df = df.join(atr_trail(df))
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
    stop_type: str               # "10 pts" or "1%": whichever was closer
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


def open_trade(side: str, signal_time, ts, e: float) -> Trade:
    pct = e * SL_PCT / 100
    if side == "BUY":
        stop = max(e - SL_POINTS, e - pct)
        target = e + TARGET_POINTS
    else:
        stop = min(e + SL_POINTS, e + pct)
        target = e - TARGET_POINTS
    kind = "10 pts" if SL_POINTS <= pct else "1%"
    return Trade(side, signal_time, ts, e, stop, kind, target, stop, e)


def run(df: pd.DataFrame, start_date) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, H, L, C = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    BUY, SELL, WARM = (df[k].to_numpy() for k in ("trail_buy", "trail_sell", "warm"))
    tr = TRAIL_PCT / 100
    trades: list[Trade] = []
    pos: Trade | None = None
    pos_i = -1
    pending = None

    def close(ts, px, reason):
        nonlocal pos
        pos.exit_time, pos.exit, pos.reason = ts, float(px), reason
        trades.append(pos)
        pos = None

    def stop_reason(t: Trade) -> str:
        if not t.target_hit:
            return f"SL {t.stop_type}"
        return "Breakeven SL" if t.stop == t.entry else "Trailing SL"

    for i in range(len(df)):
        ts = idx[i]

        # 1) act on the previous candle's signal at this candle's open
        if pending is not None:
            side, sig_ts = pending
            if pos is not None and pos.side != side:
                close(ts, O[i], "Reverse")
            if pos is None:
                pos, pos_i = open_trade(side, sig_ts, ts, float(O[i])), i
            pending = None

        # 2) exits work from the candle after entry
        if pos is not None and i > pos_i:
            if pos.side == "BUY" and L[i] <= pos.stop:
                close(ts, min(O[i], pos.stop), stop_reason(pos))
            elif pos.side == "SELL" and H[i] >= pos.stop:
                close(ts, max(O[i], pos.stop), stop_reason(pos))

        # 3) +20 points -> breakeven, then trail 1% behind the best price (from next candle)
        if pos is not None and i > pos_i:
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

        # 4) signal on this completed candle -> act at the next open
        if i == len(df) - 1 or dates[i] < start_date or not WARM[i]:
            continue
        side = "BUY" if BUY[i] else "SELL" if SELL[i] else None
        if side is not None and (pos is None or pos.side != side):
            pending = (side, ts)

    if pos is not None:
        close(idx[-1], C[-1], "Open at end")
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
    flat = tl[tl.pnl_pts == 0]
    eq = tl.net_rs.cumsum()
    gw, gl = wins.net_rs.sum(), -losses.net_rs.sum()
    lines = [
        f"Total trades      : {len(tl)}  (BUY {sum(tl.side == 'BUY')}, SELL {sum(tl.side == 'SELL')})",
        f"Winning / losing  : {len(wins)} / {len(losses)}  (losing includes {len(flat)} at exactly entry price)",
        f"Win rate          : {100 * len(wins) / len(tl):.1f}%",
        f"Reached +{TARGET_POINTS:g} pts   : {int(tl.target_hit.sum())} trades (trailing switched on)",
        f"Initial stop      : " + ", ".join(f"{k}={v}" for k, v in tl.stop_type.value_counts().items()),
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
    ap.add_argument("--day", help="print only trades entered on this date (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    raw = load_csv(a.csv) if a.csv else fetch_1m(a.symbol, days=30)
    df = to_timeframe(clean(raw), TIMEFRAME_MIN)
    sessions = sorted(set(df.index.date))
    bar = pd.Timedelta(minutes=TIMEFRAME_MIN)
    if not a.include_today and (df.index[-1] + bar).time() < pd.Timestamp("15:15").time():
        sessions = sessions[:-1]                                           # session not finished
        df = df[df.index.date <= sessions[-1]]
    df = add_indicators(df)
    warm_from = df.index[df["warm"]][0].date()
    window = [d for d in sessions if d >= warm_from][-a.sessions:]
    trades = run(df, window[0])
    tl, lines = report(trades, a.qty, a.cost_pct)

    src = a.csv if a.csv else f"{a.symbol} (yfinance 1m -> 3m)"
    title = (f"OD SOFTWARE trades + 1% | {src} | {TIMEFRAME_MIN}m | "
             f"{window[0]} -> {window[-1]} ({len(window)} sessions)")
    header = (f"{title}\nEntry next open on the script's signal (EMA 4 x ATR-trail 7 x 1.7), reverse on "
              f"the opposite signal, stop = closer of {SL_POINTS:g} pts / {SL_PCT:g}%, at +{TARGET_POINTS:g} pts "
              f"stop to breakeven then trail {TRAIL_PCT:g}% behind the best price, held overnight.\n")
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

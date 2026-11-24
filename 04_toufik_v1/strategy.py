#!/usr/bin/env python3
"""
TOUFIK - EMA 4 / MA 10 crossover strategy backtest (3-minute candles, NSE intraday).

Indicators : EMA 4 and MA 10 (SMA by default, --ma-type ema) on close.
CE (BUY)   : EMA 4 crosses above MA 10. PE (SELL): EMA 4 crosses below MA 10.
Entry      : open of the candle after the crossover candle closes.
Reversal   : every opposite crossover exits the open position and enters the other side
             at the same open. Only one position at a time.
Stop loss  : --sl-pct (default 1%) from entry. After a stop-loss exit, wait for the next
             fresh crossover.
Session    : intraday; entries until 15:00, anything open squared off at 15:15.
Costs      : --cost-pct (round trip, % of entry value) and --brokerage (Rs per order).
Output     : trades.csv, summary.txt and chart.html (candles, EMA 4, MA 10, all entries/exits).

Usage:
    python 04_toufik_v1/strategy.py                        # RELIANCE.NS 3m, last 5 sessions
    python 04_toufik_v1/strategy.py --sl-pct 0.5 --ma-type ema
    python 04_toufik_v1/strategy.py --qty 500 --brokerage 20 --cost-pct 0.05
    python 04_toufik_v1/strategy.py --day 2026-11-17
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
from data import fetch_1m, load_csv, clean, resample  # noqa: E402
from indicators import ema as ema_ind, ma as ma_ind  # noqa: E402
from chart import make_chart  # noqa: E402

TIMEFRAME_MIN = 3
SL_PCT = 1.0
ENTRY_CUTOFF = time(15, 0)       # an entry candle must open before 15:00
SQUARE_OFF = time(15, 15)        # close of the candle ending 15:15
COST_PCT = 0.05                  # round-trip costs, % of entry value
BROKERAGE = 0.0                  # Rs per executed order (2 orders per trade)


# ---------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame, ma_type: str) -> pd.DataFrame:
    df = df.copy()
    e, m = ema_ind.ema(df), ma_ind.ma(df, ma_type=ma_type)
    df[e.name], df[m.name] = e, m
    above = e > m
    below = e < m
    # ta.crossover / ta.crossunder on completed candles
    df["bull_cross"] = above & (e.shift(1) <= m.shift(1))
    df["bear_cross"] = below & (e.shift(1) >= m.shift(1))
    df["warm"] = np.arange(len(df)) >= 3 * ma_ind.LENGTH
    return df


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str                    # CE / PE
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    stop: float
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pts(self) -> float:
        return (self.exit - self.entry) if self.side == "CE" else (self.entry - self.exit)


def run(df: pd.DataFrame, start_date, sl_pct: float) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, H, L, C = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    BX, SX, WARM = (df[k].to_numpy() for k in ("bull_cross", "bear_cross", "warm"))
    bar = pd.Timedelta(minutes=TIMEFRAME_MIN)
    sl = sl_pct / 100
    trades: list[Trade] = []
    pos: Trade | None = None
    pending = None

    def close(ts, px, reason):
        nonlocal pos
        pos.exit_time, pos.exit, pos.reason = ts, float(px), reason
        trades.append(pos)
        pos = None

    for i in range(1, len(df)):
        ts = idx[i]
        end = (ts + bar).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) act on the previous candle's crossover at this candle's open (same day only)
        if pending is not None and dates[i - 1] == dates[i]:
            if pending["exit"] and pos is not None:
                close(ts, O[i], "Opposite crossover")
            if pending["enter"] and pos is None and ts.time() < ENTRY_CUTOFF:
                side = pending["enter"]
                stop = O[i] * (1 - sl) if side == "CE" else O[i] * (1 + sl)
                pos = Trade(side, pending["signal_time"], ts, float(O[i]), float(stop))
        pending = None

        # 2) stop loss inside the candle
        if pos is not None:
            if pos.side == "CE" and L[i] <= pos.stop:
                close(ts, min(O[i], pos.stop), "StopLoss")
            elif pos.side == "PE" and H[i] >= pos.stop:
                close(ts, max(O[i], pos.stop), "StopLoss")

        # 3) intraday square-off
        if pos is not None and (end >= SQUARE_OFF or last_of_day):
            close(ts, C[i], "Square-off 15:15")

        # 4) crossover on this completed candle -> act at the next open
        if dates[i] < start_date or not WARM[i] or end >= SQUARE_OFF or last_of_day:
            continue
        cross = "CE" if BX[i] else "PE" if SX[i] else None
        if cross is None:
            continue
        if pos is not None and pos.side != cross:
            pending = dict(exit=True, enter=cross, signal_time=ts)      # reversal
        elif pos is None:
            pending = dict(exit=False, enter=cross, signal_time=ts)     # fresh entry

    return trades


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int, cost_pct: float, brokerage: float):
    rows = []
    for t in trades:
        d = asdict(t)
        cost = cost_pct / 100 * t.entry * qty + 2 * brokerage
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
    for col in ("entry", "stop", "exit"):
        tl[col] = tl[col].round(2)
    wins, losses = tl[tl.net_rs > 0], tl[tl.net_rs <= 0]
    eq = tl.net_rs.cumsum()
    gw, gl = wins.net_rs.sum(), -losses.net_rs.sum()
    lines = [
        f"Total trades      : {len(tl)}  (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})",
        f"Winning / losing  : {len(wins)} / {len(losses)}",
        f"Win rate          : {100 * len(wins) / len(tl):.1f}%",
        f"Gross P&L         : {tl.pnl_pts.sum():+.2f} points per share = Rs {tl.gross_rs.sum():+,.2f} (qty {qty})",
        f"Costs             : Rs {tl.cost_rs.sum():,.2f} ({cost_pct}% round trip + Rs {brokerage} per order)",
        f"Net P&L           : Rs {tl.net_rs.sum():+,.2f}",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        f"Max drawdown      : Rs {(eq - eq.cummax().clip(lower=0)).min():,.2f}",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    return tl, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="RELIANCE.NS")
    ap.add_argument("--csv", help="load 1-minute OHLC from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=5, help="trading sessions to backtest (max ~20)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--sl-pct", type=float, default=SL_PCT, help="stop loss in %% of entry")
    ap.add_argument("--ma-type", choices=["sma", "ema"], default=ma_ind.TYPE, help="type of the MA 10")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--cost-pct", type=float, default=COST_PCT, help="round-trip cost, %% of entry value")
    ap.add_argument("--brokerage", type=float, default=BROKERAGE, help="Rs per executed order")
    ap.add_argument("--day", help="print only this date's trades (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    raw = load_csv(a.csv) if a.csv else fetch_1m(a.symbol, days=int(a.sessions * 1.6) + 6)
    df = resample(clean(raw), TIMEFRAME_MIN)
    sessions = sorted(set(df.index.date))
    if not a.include_today and df.index[-1].time() < SQUARE_OFF:
        sessions = sessions[:-1]
        df = df[df.index.date <= sessions[-1]]
    window = sessions[-a.sessions:]
    df = add_indicators(df, a.ma_type)
    trades = run(df, window[0], a.sl_pct)
    tl, lines = report(trades, a.qty, a.cost_pct, a.brokerage)

    e_col, m_col = f"ema{ema_ind.LENGTH}", f"ma{ma_ind.LENGTH}"
    title = (f"TOUFIK EMA {ema_ind.LENGTH} / MA {ma_ind.LENGTH} ({a.ma_type.upper()}) | {a.symbol} "
             f"{TIMEFRAME_MIN}m | {window[0]} -> {window[-1]} ({len(window)} sessions)")
    header = (f"{title}\nEntry next open after a crossover, reverse on every opposite crossover, "
              f"SL {a.sl_pct}%, entries until {ENTRY_CUTOFF:%H:%M}, exit by {SQUARE_OFF:%H:%M}.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")
    view = df[df.index.date >= window[0]]
    view.to_csv(os.path.join(a.out, "bars_with_indicators.csv"))
    chart_path = os.path.join(a.out, "chart.html")
    try:
        make_chart(view, tl, lines, title, chart_path, e_col, m_col)
    except ImportError:
        chart_path = "(install plotly for the chart: pip install plotly)"

    print(header)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "signal_time", "entry_time", "entry", "stop", "exit_time", "exit",
                    "reason", "pnl_pts", "net_rs"]].to_string(index=False))
    print("\n" + "\n".join(lines))
    print(f"\nChart: {chart_path}")


if __name__ == "__main__":
    main()

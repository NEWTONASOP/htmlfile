#!/usr/bin/env python3
"""
AMIT RAJDEV - 5-minute reversal strategy backtest (NSE intraday).

Conditions (evaluated on each completed 5-minute candle):
  1. SMA 120 (close)           BUY: close > SMA 120          SELL: close < SMA 120
  2. LuxAlgo pivots (50)       BUY: latest pivot label is a Low       SELL: a High
  3. Reversal Entry Zones      BUY: latest label Bullish Reversal     SELL: Bearish Reversal
     (Low, Average)
     (2 and 3 change on the candle where the label sits on the chart)
  4. Smoothed Heiken Ashi v1   BUY: candle Green              SELL: candle Red
Entry : all 4 newly aligned on a candle close (not aligned on the previous candle) and no
        open position -> enter at the next candle open. Entries up to the 15:00 candle open.
Exit  : exit at the next open once 2+ conditions have turned against the trade (bearish for
        a BUY, bullish for a SELL) at any candle close since entry, even if one turned back.
        They do not need to change together. No reverse entry.
Risk  : quantity 1, no stop loss, square-off 15:15. Signals are not carried overnight.

Usage:
    python amitrajdev/strategy.py                    # RELIANCE.NS 5m, last 5 sessions
    python amitrajdev/strategy.py --sessions 20
    python amitrajdev/strategy.py --day 2026-11-17
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
from data import fetch_yf, load_csv, clean  # noqa: E402
from indicators import sma as sma_ind  # noqa: E402
from indicators.luxalgo_pivots import lux_pivots, LENGTH as LUX_LEN  # noqa: E402
from indicators.reversal_entry_zones import reversal_entry_zones  # noqa: E402
from indicators.smoothed_heiken_ashi import smoothed_heiken_ashi  # noqa: E402
from chart import make_chart  # noqa: E402

BAR = pd.Timedelta(minutes=5)
LAST_ENTRY_OPEN = time(15, 0)    # entry candle may open at 15:00 at the latest
SQUARE_OFF = time(15, 15)        # close of the 15:10 candle
QTY = 1
COND_NAMES = ["SMA120", "LuxPivot", "RevZones", "SmoothHA"]


# ---------------------------------------------------------------- indicators
def _label_state(n: int, positions, values) -> np.ndarray:
    """State that changes at each label's chart position (later labels win), carried forward."""
    arr = np.zeros(n)
    arr[:] = np.nan
    for pos, val in zip(positions, values):
        arr[int(pos)] = val
    out = pd.Series(arr).ffill().fillna(0).astype(int).to_numpy()
    return out


def add_indicators(df: pd.DataFrame):
    """LuxAlgo pivot and Reversal Entry Zones conditions change on the candle where their
    label sits on the chart (pivot candle / turning point, missed pivots included)."""
    df = df.copy()
    df["sma120"] = sma_ind.sma(df)
    _, lux_events = lux_pivots(df)
    df = pd.concat([df, reversal_entry_zones(df), smoothed_heiken_ashi(df)], axis=1)
    ev = lux_events.sort_values("pivot_idx", kind="stable")
    df["lux_state"] = _label_state(len(df), ev.pivot_idx, np.where(ev.kind == "low", 1, -1))
    rz = df[df.rez_signal != 0]
    df["rez_last"] = _label_state(len(df), rz.rez_pivot_idx, rz.rez_signal)

    # +1 bullish, -1 bearish, 0 neutral/unknown, per condition
    c1 = np.sign(df["Close"] - df["sma120"]).fillna(0).astype(int)
    c4 = np.where(df["ha_open"].isna(), 0, np.where(df["ha_green"], 1, -1))
    df["c_SMA120"], df["c_LuxPivot"], df["c_RevZones"], df["c_SmoothHA"] = c1, df["lux_state"], df["rez_last"], c4
    conds = df[[f"c_{c}" for c in COND_NAMES]]
    df["all_bull"] = (conds == 1).all(axis=1)
    df["all_bear"] = (conds == -1).all(axis=1)
    df["new_bull"] = df["all_bull"] & ~df["all_bull"].shift(1, fill_value=False)
    df["new_bear"] = df["all_bear"] & ~df["all_bear"].shift(1, fill_value=False)
    df["warm"] = df["sma120"].notna() & df["ha_open"].notna() & (df["lux_state"] != 0) & (df["rez_last"] != 0)
    return df, lux_events


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    exit_signal_time: pd.Timestamp | None = None
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pts(self) -> float:
        return (self.exit - self.entry) if self.side == "BUY" else (self.entry - self.exit)


def run(df: pd.DataFrame, start_date) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, C = df["Open"].to_numpy(), df["Close"].to_numpy()
    conds = df[[f"c_{c}" for c in COND_NAMES]].to_numpy()
    NB, NS, WARM = (df[k].to_numpy() for k in ("new_bull", "new_bear", "warm"))
    trades: list[Trade] = []
    pos: Trade | None = None
    against: set = set()
    pending = None

    for i in range(1, len(df)):
        ts = idx[i]
        end = (ts + BAR).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) orders from the previous close fill at this open (same day only)
        if pending is not None and dates[i - 1] == dates[i]:
            if pending[0] == "exit" and pos is not None:
                pos.exit_time, pos.exit, pos.reason = ts, float(O[i]), pending[2]
                pos.exit_signal_time = pending[1]
                trades.append(pos)
                pos = None
            elif pending[0] in ("BUY", "SELL") and pos is None and ts.time() <= LAST_ENTRY_OPEN:
                pos = Trade(pending[0], pending[1], ts, float(O[i]))
                against = set()
        pending = None

        # 2) square-off
        if pos is not None and (end >= SQUARE_OFF or last_of_day):
            pos.exit_time, pos.exit, pos.reason = ts, float(C[i]), "Square-off 15:15"
            trades.append(pos)
            pos = None

        # 3) evaluate on this candle's close
        if dates[i] < start_date or not WARM[i] or end >= SQUARE_OFF or last_of_day:
            continue
        if pos is not None:
            bad = -1 if pos.side == "BUY" else 1
            now = {COND_NAMES[k] for k in range(4) if conds[i, k] == bad}
            against |= now
            hits = against
            if len(hits) >= 2:
                word = "bearish" if pos.side == "BUY" else "bullish"
                pending = ("exit", ts, f"{len(hits)} {word}: " + "+".join(sorted(hits)))
        elif NB[i]:
            pending = ("BUY", ts)
        elif NS[i]:
            pending = ("SELL", ts)
    return trades


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int, cost_pct: float):
    rows = []
    for t in trades:
        d = asdict(t)
        d["pnl_pts"] = round(t.pnl_pts, 2)
        d["net_rs"] = round(t.pnl_pts * qty - cost_pct / 100 * t.entry * qty, 2)
        rows.append(d)
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, ["Total trades      : 0"]
    for col in ("signal_time", "entry_time", "exit_signal_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    tl["exit"] = tl["exit"].round(2)
    tl["entry"] = tl["entry"].round(2)
    wins, losses = tl[tl.net_rs > 0], tl[tl.net_rs <= 0]
    gw, gl = wins.net_rs.sum(), -losses.net_rs.sum()
    lines = [
        f"Total trades      : {len(tl)}  (BUY {sum(tl.side == 'BUY')}, SELL {sum(tl.side == 'SELL')})",
        f"Winning / losing  : {len(wins)} / {len(losses)}",
        f"Win rate          : {100 * len(wins) / len(tl):.1f}%",
        f"Net P&L           : {tl.pnl_pts.sum():+.2f} points = Rs {tl.net_rs.sum():+,.2f} (qty {qty}, cost {cost_pct}%)",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        "Exits             : " + ", ".join(f"{k}={v}" for k, v in
                                           tl.reason.str.split(": ").str[0].value_counts().items()),
    ]
    return tl, lines


def status_lines(df: pd.DataFrame) -> list[str]:
    r = df.iloc[-1]
    txt = {1: "BUY", -1: "SELL", 0: "-"}
    detail = {
        "SMA120": f"close {r.Close:.2f} vs SMA 120 {r.sma120:.2f}",
        "LuxPivot": "latest pivot " + {1: "Low", -1: "High", 0: "none"}[int(r.lux_state)],
        "RevZones": "Last Signal " + {1: "Bullish Reversal", -1: "Bearish Reversal", 0: "Waiting"}[int(r.rez_last)],
        "SmoothHA": "candle " + ("Green" if r.ha_green else "Red"),
    }
    out = [f"Status at {df.index[-1]:%Y-%m-%d %H:%M} close:"]
    for c in COND_NAMES:
        out.append(f"  {c:<9}: {txt[int(r[f'c_{c}'])]:<4}  ({detail[c]})")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="RELIANCE.NS")
    ap.add_argument("--csv", help="load 5m OHLC from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=5, help="trading sessions to backtest (5 = one week)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--qty", type=int, default=QTY)
    ap.add_argument("--cost-pct", type=float, default=0.0, help="round-trip cost, %% of entry value")
    ap.add_argument("--day", help="print only this date's trades (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    df = clean(load_csv(a.csv) if a.csv else fetch_yf(a.symbol, period="60d", interval="5m"))
    sessions = sorted(set(df.index.date))
    if not a.include_today and df.index[-1].time() < SQUARE_OFF:
        sessions = sessions[:-1]
        df = df[df.index.date <= sessions[-1]]
    window = sessions[-a.sessions:]
    df, lux_events = add_indicators(df)
    trades = run(df, window[0])
    tl, lines = report(trades, a.qty, a.cost_pct)
    status = status_lines(df)

    title = (f"AMIT RAJDEV 5m reversal | {a.symbol} | {window[0]} -> {window[-1]} "
             f"({len(window)} sessions)")
    header = (f"{title}\nEntry next open when all 4 newly align (until the 15:00 open), "
              f"no SL, square-off {SQUARE_OFF:%H:%M}, qty {a.qty}.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n\n" + "\n".join(status) + "\n")
    view = df[df.index.date >= window[0]]
    view.to_csv(os.path.join(a.out, "bars_with_indicators.csv"))
    chart_path = os.path.join(a.out, "chart.html")
    try:
        make_chart(df, view, lux_events, tl, lines + [""] + status, title, chart_path, COND_NAMES)
    except ImportError:
        chart_path = "(install plotly for the chart: pip install plotly)"

    print(header)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "signal_time", "entry_time", "entry", "exit_signal_time", "exit_time",
                    "exit", "reason", "pnl_pts"]].to_string(index=False))
    print("\n" + "\n".join(lines))
    print("\n" + "\n".join(status))
    print(f"\nChart: {chart_path}")


if __name__ == "__main__":
    main()

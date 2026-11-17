#!/usr/bin/env python3
"""
ASHISHKUMARVERMA - ORB (Opening Range Breakout) strategy backtest, NSE intraday.

Levels   : 15-minute candles. ORB candle 09:15-09:30 (ORB High/Low), alert candle
           09:30-09:45 (Alert High/Low). Alert close > ORB High = CE setup,
           < ORB Low = PE setup, otherwise no trade that day.
Entry    : after 09:45, the moment the SPOT price breaks the alert candle
           (CE above Alert High, PE below Alert Low), checked on 1-minute candles;
           no waiting for a candle close. Only the setup's direction is traded.
Stop loss: CE = Alert Low, PE = Alert High, capped at --max-sl-pct (1%) of the entry.
Target   : --rr x risk (default 1:1).
Rules    : at most one trade per day, no re-entry; entries until --last-entry
           (default 15:00); square-off 15:15. All prices are the underlying spot.

Usage:
    python ashishkumarverma/strategy.py                    # RELIANCE.NS, last 5 sessions
    python ashishkumarverma/strategy.py --rr 2 --max-sl-pct 0.75
    python ashishkumarverma/strategy.py --symbol ^NSEI     # NIFTY 50 spot
    python ashishkumarverma/strategy.py --sessions 20 --qty 500 --cost-pct 0.05
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, asdict
from datetime import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_1m, load_csv, clean, resample  # noqa: E402
from indicators.orb import orb_levels  # noqa: E402

ENTRY_START = time(9, 45)
LAST_ENTRY = "15:00"
SQUARE_OFF = time(15, 15)
RR = 1.0
MAX_SL_PCT = 1.0
COST_PCT = 0.05


@dataclass
class Trade:
    date: object
    side: str
    entry_time: pd.Timestamp
    entry: float
    alert_sl: float      # alert candle low (CE) / high (PE)
    stop: float          # after the 1% cap
    target: float
    sl_capped: bool
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pts(self) -> float:
        return (self.exit - self.entry) if self.side == "CE" else (self.entry - self.exit)


def run_day(m1: pd.DataFrame, lv: pd.Series, rr: float, cap: float, last_entry: time) -> Trade | None:
    """Simulate one day on 1-minute spot candles. Stop is checked before target in a candle."""
    side = lv.setup
    bars = m1[(m1.index.time >= ENTRY_START)]
    t: Trade | None = None
    for ts, b in bars.iterrows():
        end = (ts + pd.Timedelta(minutes=1)).time()
        if t is None:
            if ts.time() >= last_entry or end > SQUARE_OFF:
                return None                                   # no breakout in time
            if side == "CE" and b.High > lv.alert_high:
                px = max(b.Open, lv.alert_high)
                stop = max(lv.alert_low, px * (1 - cap))
                t = Trade(lv.name, "CE", ts, px, lv.alert_low, stop, px + rr * (px - stop),
                          stop > lv.alert_low)
            elif side == "PE" and b.Low < lv.alert_low:
                px = min(b.Open, lv.alert_low)
                stop = min(lv.alert_high, px * (1 + cap))
                t = Trade(lv.name, "PE", ts, px, lv.alert_high, stop, px - rr * (stop - px),
                          stop < lv.alert_high)
            else:
                continue
        # manage the open trade (including the entry candle)
        if t.side == "CE":
            if b.Low <= t.stop:
                t.exit_time, t.exit, t.reason = ts, min(b.Open, t.stop) if ts != t.entry_time else t.stop, "StopLoss"
                return t
            if b.High >= t.target:
                t.exit_time, t.exit, t.reason = ts, max(b.Open, t.target) if ts != t.entry_time else t.target, "Target"
                return t
        else:
            if b.High >= t.stop:
                t.exit_time, t.exit, t.reason = ts, max(b.Open, t.stop) if ts != t.entry_time else t.stop, "StopLoss"
                return t
            if b.Low <= t.target:
                t.exit_time, t.exit, t.reason = ts, min(b.Open, t.target) if ts != t.entry_time else t.target, "Target"
                return t
        if end >= SQUARE_OFF:
            t.exit_time, t.exit, t.reason = ts, b.Close, "Square-off 15:15"
            return t
    if t is not None:                                         # data ended early
        t.exit_time, t.exit, t.reason = bars.index[-1], bars.Close.iloc[-1], "End of data"
    return t


def report(trades: list[Trade], days: pd.DataFrame, qty: int, cost_pct: float):
    rows = []
    for t in trades:
        d = asdict(t)
        cost = cost_pct / 100 * t.entry * qty
        d["pnl_pts"] = round(t.pnl_pts, 2)
        d["net_rs"] = round(t.pnl_pts * qty - cost, 2)
        rows.append(d)
    tl = pd.DataFrame(rows)
    n_ce, n_pe = (days.setup == "CE").sum(), (days.setup == "PE").sum()
    head = [f"Days              : {len(days)}  (CE setups {n_ce}, PE setups {n_pe}, "
            f"no-trade {len(days) - n_ce - n_pe})"]
    if tl.empty:
        return tl, head + ["Trades            : 0"]
    for col in ("entry_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M")
    for col in ("entry", "alert_sl", "stop", "target", "exit"):
        tl[col] = tl[col].astype(float).round(2)
    wins, losses = tl[tl.net_rs > 0], tl[tl.net_rs <= 0]
    gw, gl = wins.net_rs.sum(), -losses.net_rs.sum()
    lines = head + [
        f"Trades            : {len(tl)}  (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')}; "
        f"setups without a breakout: {n_ce + n_pe - len(tl)})",
        f"Winning / losing  : {len(wins)} / {len(losses)}  (win rate {100 * len(wins) / len(tl):.1f}%)",
        f"Gross P&L         : {tl.pnl_pts.sum():+.2f} points per share",
        f"Net P&L           : Rs {tl.net_rs.sum():+,.2f}  (qty {qty}, cost {cost_pct}% round trip)",
        f"Profit factor     : {gw / gl:.2f}" if gl > 0 else "Profit factor     : inf",
        f"SL capped at 1%   : {int(tl.sl_capped.sum())} trades",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    return tl, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="RELIANCE.NS", help="underlying spot, e.g. RELIANCE.NS or ^NSEI")
    ap.add_argument("--csv", help="load 1-minute OHLC from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=5, help="trading days to backtest (max ~20)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--rr", type=float, default=RR, help="target as a multiple of risk (1 = 1:1)")
    ap.add_argument("--max-sl-pct", type=float, default=MAX_SL_PCT, help="cap on SL distance, %% of entry")
    ap.add_argument("--last-entry", default=LAST_ENTRY, help="no new entry from this time (HH:MM)")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--cost-pct", type=float, default=COST_PCT, help="round-trip cost, %% of entry value")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()
    last_entry = time(*map(int, a.last_entry.split(":")))

    raw = load_csv(a.csv) if a.csv else fetch_1m(a.symbol, days=int(a.sessions * 1.6) + 6)
    m1 = clean(raw)
    sessions = sorted(set(m1.index.date))
    if not a.include_today and m1.index[-1].time() < SQUARE_OFF:
        sessions = sessions[:-1]
    window = sessions[-a.sessions:]
    m1 = m1[pd.Index(m1.index.date).isin(window)]
    days = orb_levels(resample(m1, 15))

    trades = []
    for day, lv in days.iterrows():
        if lv.setup in ("CE", "PE"):
            t = run_day(m1[m1.index.date == day], lv, a.rr, a.max_sl_pct / 100, last_entry)
            if t is not None:
                trades.append(t)
    tl, lines = report(trades, days, a.qty, a.cost_pct)

    header = (f"ASHISHKUMARVERMA ORB | {a.symbol} spot | 15m levels, 1m breakout | "
              f"{window[0]} -> {window[-1]} ({len(window)} sessions)\n"
              f"Entry on break of the alert candle after 09:45 (until {last_entry:%H:%M}), "
              f"SL alert candle capped at {a.max_sl_pct}%, target 1:{a.rr:g}, one trade a day, "
              f"square-off {SQUARE_OFF:%H:%M}.\n")
    os.makedirs(a.out, exist_ok=True)
    days.round(2).to_csv(os.path.join(a.out, "days.csv"))
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")

    print(header)
    show = days[["orb_high", "orb_low", "alert_high", "alert_low", "alert_close", "setup"]].copy() \
        if "orb_high" in days else days
    print("Levels per day:")
    print(show.round(2).fillna("-").to_string())
    if not tl.empty:
        print("\nTrades:")
        print(tl[["date", "side", "entry_time", "entry", "stop", "target", "sl_capped",
                  "exit_time", "exit", "reason", "pnl_pts", "net_rs"]].to_string(index=False))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

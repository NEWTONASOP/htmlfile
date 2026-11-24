#!/usr/bin/env python3
"""
ASHISHKUMARVERMA - ORB strategy backtest (updated spec), NSE intraday, spot prices.

Levels   : 15-minute candles. Opening candle 09:15-09:30 -> Opening High / Low.
Filters  : no trade if |gap| > 2% (09:15 open vs previous close), or RVOL(20) < 1.5 on the
           opening candle or on the alert candle. RVOL = candle volume / average volume of
           the same 15-minute slot over the previous 20 trading days (FYERS, option B).
Alert    : the first 15-minute candle (any time) that CLOSES above Opening High (CE) or
           below Opening Low (PE). Its high / low are the breakout levels.
Entry    : any time after the alert candle closes, the first 15-minute candle that trades
           above Alert High (CE) / below Alert Low (PE). Entry is immediate, at the level
           itself (as a stop order fills), or at the candle open if it opens beyond it.
           No entry from 13:30 (the breakout candle must start before 13:30).
           One trade per day, no re-entry.
Stop loss: Alert Low (CE) / Alert High (PE), capped at 1% from the entry. On the entry
           candle itself, a touch of the stop counts (cautious: the order inside the candle
           is unknown).
Exit     : CE when a 15-minute candle closes below the 9 EMA, PE when one closes above it,
           at the next 15-minute candle open; or the stop loss; or square-off at 15:00.
           No fixed target (--rr adds one if wanted).

Usage:
    python 05_ashishkumarverma_v1/strategy.py                   # RELIANCE.NS, last 5 sessions
    python 05_ashishkumarverma_v1/strategy.py --sessions 40     # about two months
    python 05_ashishkumarverma_v1/strategy.py --rr 2            # optional fixed 1:2 target
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
from data import fetch_15m, load_csv, clean  # noqa: E402
from indicators.orb import day_levels  # noqa: E402
from indicators.rvol import rvol_slot, rvol_rolling, LENGTH as RVOL_LEN, MIN_RVOL  # noqa: E402
from indicators.ema import ema, LENGTH as EMA_LEN  # noqa: E402

LAST_ENTRY = "13:30"        # the breakout candle must start before this
SQUARE_OFF = time(15, 0)    # close of the 14:45 candle
MAX_GAP_PCT = 2.0
MAX_SL_PCT = 1.0
M15 = pd.Timedelta(minutes=15)


@dataclass
class Trade:
    date: object
    side: str
    alert_time: pd.Timestamp
    entry_time: pd.Timestamp     # breakout candle (filled at the level during it)
    entry: float
    stop: float
    sl_capped: bool
    target: float | None
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""

    @property
    def pnl_pts(self) -> float:
        return (self.exit - self.entry) if self.side == "CE" else (self.entry - self.exit)


def run_day(c15_day: pd.DataFrame, lv: dict, a) -> Trade | None:
    """Simulate one day on 15-minute candles after the alert candle."""
    side = lv["setup"]
    ce = side == "CE"
    last_entry = time(*map(int, a.last_entry.split(":")))
    cap = a.max_sl_pct / 100
    bars = c15_day[c15_day.index > lv["alert_time"]]
    t: Trade | None = None
    ema_exit = None                                   # candle whose close crossed the EMA
    for ts, b in bars.iterrows():
        end = (ts + M15).time()
        if t is None:
            if ts.time() >= last_entry:
                return None                           # no breakout before 13:30
            if ce and b.High > lv["alert_high"]:
                px = max(float(b.Open), lv["alert_high"])
                stop = max(lv["alert_low"], px * (1 - cap))
                tgt = px + a.rr * (px - stop) if a.rr else None
            elif not ce and b.Low < lv["alert_low"]:
                px = min(float(b.Open), lv["alert_low"])
                stop = min(lv["alert_high"], px * (1 + cap))
                tgt = px - a.rr * (stop - px) if a.rr else None
            else:
                continue
            t = Trade(lv["date"], side, lv["alert_time"], ts, px, float(stop),
                      bool(stop != (lv["alert_low"] if ce else lv["alert_high"])), tgt)
        else:
            # 9 EMA exit decided at the previous close -> exit at this candle's open
            if ema_exit is not None:
                t.exit_time, t.exit = ts, float(b.Open)
                t.reason = f"15m close {'below' if ce else 'above'} 9 EMA ({ema_exit:%H:%M} candle)"
                return t
        # stop loss, then optional target, inside the candle (entry candle included)
        if (b.Low <= t.stop) if ce else (b.High >= t.stop):
            fill = t.stop if ts == t.entry_time else (min(b.Open, t.stop) if ce else max(b.Open, t.stop))
            t.exit_time, t.exit, t.reason = ts, float(fill), "StopLoss"
            return t
        if t.target is not None and ((b.High >= t.target) if ce else (b.Low <= t.target)):
            t.exit_time, t.exit, t.reason = ts, float(t.target), f"Target 1:{a.rr:g}"
            return t
        if end >= SQUARE_OFF:
            t.exit_time, t.exit, t.reason = ts, float(b.Close), "Square-off 15:00"
            return t
        if (ce and b.Close < b.ema) or (not ce and b.Close > b.ema):
            ema_exit = ts
    if t is not None:
        t.exit_time, t.exit, t.reason = bars.index[-1], float(bars.Close.iloc[-1]), "End of data"
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="RELIANCE.NS", help="stock (needs volume for RVOL)")
    ap.add_argument("--csv", help="load 15-minute OHLCV from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=5,
                    help="trading days to backtest (max ~40: 60 days of data minus 20 for RVOL)")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--min-rvol", type=float, default=MIN_RVOL)
    ap.add_argument("--rvol-mode", choices=["slot", "candles"], default="slot",
                    help="slot: same time slot over the previous 20 days (default); "
                         "candles: average of the last 20 candles")
    ap.add_argument("--max-gap-pct", type=float, default=MAX_GAP_PCT)
    ap.add_argument("--max-sl-pct", type=float, default=MAX_SL_PCT)
    ap.add_argument("--last-entry", default=LAST_ENTRY, help="no entry from this time (HH:MM)")
    ap.add_argument("--rr", type=float, default=None, help="optional fixed target (default: none)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    c15 = clean(load_csv(a.csv) if a.csv else fetch_15m(a.symbol))   # 15-minute candles, ~60 days
    sessions = sorted(set(c15.index.date))
    if not a.include_today and (c15.index[-1] + M15).time() < time(15, 30):
        sessions = sessions[:-1]
        c15 = c15[c15.index.date <= sessions[-1]]
    window = sessions[-a.sessions:]
    c15["ema"] = ema(c15)
    c15["rvol"] = rvol_slot(c15) if a.rvol_mode == "slot" else rvol_rolling(c15)

    days, trades = [], []
    for day in window:
        prev = c15[c15.index.date < day]
        prev_close = float(prev.Close.iloc[-1]) if len(prev) else float("nan")
        lv = day_levels(c15[c15.index.date == day], prev_close)
        lv["date"] = day
        reason = None
        if lv.get("open_high") is None:
            reason = lv["note"]
        elif lv["open_rvol"] != lv["open_rvol"] or lv["gap_pct"] != lv["gap_pct"]:
            reason = f"Not enough history for RVOL({RVOL_LEN}) / gap"
        elif abs(lv["gap_pct"]) > a.max_gap_pct:
            reason = f"Gap {lv['gap_pct']:+.2f}% beyond {a.max_gap_pct}%"
        elif not lv["open_rvol"] >= a.min_rvol:
            reason = f"Opening candle RVOL {lv['open_rvol']:.2f} < {a.min_rvol}"
        elif lv["setup"] is None:
            reason = lv["note"]
        elif not lv["alert_rvol"] >= a.min_rvol:
            reason = f"Alert candle RVOL {lv['alert_rvol']:.2f} < {a.min_rvol}"
        elif (lv["alert_time"] + M15).time() > time(*map(int, a.last_entry.split(":"))):
            reason = "Alert candle closed after the last entry time"
        t = None
        if reason is None:
            t = run_day(c15[c15.index.date == day], lv, a)
            reason = "Traded" if t else f"No break of Alert {'High' if lv['setup'] == 'CE' else 'Low'} before {a.last_entry}"
        if t:
            trades.append(t)
        days.append(dict(date=day, gap_pct=lv.get("gap_pct"), open_high=lv.get("open_high"),
                         open_low=lv.get("open_low"), open_rvol=lv.get("open_rvol"), setup=lv.get("setup"),
                         alert_time=lv["alert_time"].strftime("%H:%M") if lv.get("alert_time") is not None else None,
                         alert_high=lv.get("alert_high"), alert_low=lv.get("alert_low"),
                         alert_rvol=lv.get("alert_rvol"), result=reason))

    dl = pd.DataFrame(days).set_index("date")
    tl = pd.DataFrame([dict(asdict(t), pnl_pts=round(t.pnl_pts, 2)) for t in trades])
    if not tl.empty:
        for col in ("alert_time", "entry_time", "exit_time"):
            tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M")
        for col in ("entry", "stop", "exit"):
            tl[col] = tl[col].astype(float).round(2)

    header = (f"ASHISHKUMARVERMA ORB (updated) | {a.symbol} | {window[0]} -> {window[-1]} ({len(window)} sessions)\n"
              f"Gap <= {a.max_gap_pct}%, RVOL({RVOL_LEN}, {'same slot, 20 days' if a.rvol_mode == 'slot' else 'last 20 candles'}) "
              f">= {a.min_rvol} on opening and alert candles, "
              f"entry on 15m break (at the level) until {a.last_entry}, SL alert candle capped {a.max_sl_pct}%, "
              f"exit on 15m close across EMA {EMA_LEN} / SL / square-off {SQUARE_OFF:%H:%M}"
              f"{f', target 1:{a.rr:g}' if a.rr else ', no fixed target'}.\n")
    wins = int((tl.pnl_pts > 0).sum()) if not tl.empty else 0
    lines = [f"Days              : {len(dl)}  (traded {len(tl)})",
             f"Trades            : {len(tl)}" + (f"  (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})" if len(tl) else "")]
    if len(tl):
        lines += [f"Winning / losing  : {wins} / {len(tl) - wins}  (win rate {100 * wins / len(tl):.1f}%)",
                  f"Net P&L           : {tl.pnl_pts.sum():+.2f} points per share (before costs)",
                  "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in
                                                     tl.reason.str.split(" \\(").str[0].value_counts().items())]

    os.makedirs(a.out, exist_ok=True)
    dl.round(2).to_csv(os.path.join(a.out, "days.csv"))
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")

    pd.set_option("display.width", 220, "display.max_columns", 20)
    print(header)
    print("Day by day:")
    print(dl.round(2).fillna("-").to_string())
    if len(tl):
        print("\nTrades:")
        print(tl[["date", "side", "alert_time", "entry_time", "entry", "stop", "sl_capped",
                  "exit_time", "exit", "reason", "pnl_pts"]].to_string(index=False))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

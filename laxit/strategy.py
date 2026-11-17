#!/usr/bin/env python3
"""
LAXIT - intraday strategy backtest (5-minute candles by default, NSE).

Indicators : SMA 20 of High, SMA 20 of Low, MACD (TradingView built-in: EMA 12 - EMA 26
             of close, signal = EMA 9 of MACD, crossover = histogram crossing 0).
             See laxit/indicators/ (Python ports + original Pine source).
CALL setup : green candle, more than 50% of its body above SMA20 High, and a bullish
             MACD crossover on this candle or the 2 before it (MACD still above signal).
PUT setup  : red candle, more than 50% of its body below SMA20 Low, bearish crossover
             on this candle or the 2 before it (MACD still below signal).
Entry      : only the next candle; CALL on a break above the setup high, PUT on a break
             below the setup low. Entries 09:45 - 14:20 IST.
Stop loss  : CALL = SMA20 Low, PUT = SMA20 High (value on the setup candle).
Management : at 1:1 book 50%, move SL to cost, then trail the rest with the SMA line
             (CALL: SMA20 Low, PUT: SMA20 High), never loosening. Forced exit 15:15.

Usage:
    python laxit/strategy.py                        # RELIANCE.NS 5m, last 5 complete sessions
    python laxit/strategy.py --interval 2m          # same rules on 2-minute candles
    python laxit/strategy.py --sessions 40 --cost-pct 0.05
    python laxit/strategy.py --one-at-a-time        # no CALL/PUT overlap
    python laxit/strategy.py --day 2026-11-13       # print only that day's trades
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
from indicators import macd as macd_ind, sma_bands  # noqa: E402

CROSS_LOOKBACK = 3            # crossover on the setup candle or the 2 before it
BODY_BEYOND = 0.5             # more than 50% of the body beyond the SMA
ENTRY_START = time(9, 45)     # entry candle may start at 09:45 ...
ENTRY_END = time(14, 20)      # ... and must end by 14:20
SQUARE_OFF = time(15, 15)     # forced exit at the close of the candle ending 15:15
BAR_MIN = 5                   # set from --interval


# ---------------------------------------------------------------- indicators
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = pd.concat([df, sma_bands.sma_bands(df), macd_ind.macd(df)], axis=1)
    o, c = df["Open"], df["Close"]
    above, below = df["macd"] > df["macd_sig"], df["macd"] < df["macd_sig"]
    recent_bull = df["bull_cross"].rolling(CROSS_LOOKBACK, min_periods=1).max().astype(bool) & above
    recent_bear = df["bear_cross"].rolling(CROSS_LOOKBACK, min_periods=1).max().astype(bool) & below

    body = (c - o).abs()
    green, red = c > o, c < o
    # share of the body beyond the SMA, e.g. CALL: part of [open, close] above sma_h
    up_part = (c - np.maximum(o, df["sma_h"])).clip(lower=0)
    dn_part = (np.minimum(o, df["sma_l"]) - c).clip(lower=0)
    df["call_setup"] = green & (up_part > BODY_BEYOND * body) & recent_bull
    df["put_setup"] = red & (dn_part > BODY_BEYOND * body) & recent_bear
    df["warm"] = np.arange(len(df)) >= macd_ind.warmup_bars()
    return df


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str
    setup_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    t1_time: pd.Timestamp | None = None
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    sl: float = 0.0          # live stop (moves after T1)

    def pnl_pts(self) -> float:
        d = 1 if self.side == "CALL" else -1
        if self.t1_time is None:
            return d * (self.exit - self.entry)
        return 0.5 * d * (self.target - self.entry) + 0.5 * d * (self.exit - self.entry)


def run(df: pd.DataFrame, start_date, independent: bool = True) -> list[Trade]:
    idx, dates = df.index, df.index.date
    O, H, L, C = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    SMAH, SMAL = df["sma_h"].to_numpy(), df["sma_l"].to_numpy()
    CS, PS, WARM = df["call_setup"].to_numpy(), df["put_setup"].to_numpy(), df["warm"].to_numpy()
    open_pos: list[Trade] = []
    done: list[Trade] = []

    def close(t: Trade, ts, px, reason):
        t.exit_time, t.exit, t.reason = ts, float(px), reason
        open_pos.remove(t)
        done.append(t)

    for i in range(1, len(df)):
        ts = idx[i]
        start, end = ts.time(), (ts + pd.Timedelta(minutes=BAR_MIN)).time()
        last_of_day = i == len(df) - 1 or dates[i + 1] != dates[i]

        # 1) entry: break of the previous (setup) candle, this candle only
        j = i - 1
        if (dates[j] == dates[i] and dates[i] >= start_date and WARM[j]
                and start >= ENTRY_START and end <= ENTRY_END):
            for side, setup, brk in (("CALL", CS[j], H[i] > H[j]), ("PUT", PS[j], L[i] < L[j])):
                busy = any(p.side == side for p in open_pos) if independent else bool(open_pos)
                if setup and brk and not busy:
                    if side == "CALL":
                        px = max(O[i], H[j]); sl = SMAL[j]; tgt = px + (px - sl)
                    else:
                        px = min(O[i], L[j]); sl = SMAH[j]; tgt = px - (sl - px)
                    if (side == "CALL" and sl < px) or (side == "PUT" and sl > px):
                        open_pos.append(Trade(side, idx[j], ts, float(px), float(sl), float(tgt), sl=float(sl)))

        # 2) manage open trades on this candle (stop checked before target)
        for t in list(open_pos):
            call = t.side == "CALL"
            hit_sl = L[i] <= t.sl if call else H[i] >= t.sl
            if hit_sl:
                px = min(O[i], t.sl) if call else max(O[i], t.sl)
                if t.t1_time is None:
                    reason = "StopLoss"
                elif abs(t.sl - t.entry) < 1e-9:
                    reason = "T1 + cost stop"
                else:
                    reason = "T1 + trailing SL"
                close(t, ts, px, reason)
                continue
            if t.t1_time is None and (H[i] >= t.target if call else L[i] <= t.target):
                t.t1_time = ts
                t.sl = t.entry               # cost-to-cost
            # 3) forced exit
            if end >= SQUARE_OFF or last_of_day:
                close(t, ts, C[i], "T1 + square-off" if t.t1_time else "Square-off 15:15")
                continue
            # 4) trail at candle close, only after T1, never loosen
            if t.t1_time is not None:
                t.sl = max(t.sl, SMAL[i]) if call else min(t.sl, SMAH[i])
    return done


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int, cost_pct: float) -> tuple[pd.DataFrame, str]:
    rows = []
    for t in trades:
        d = asdict(t)
        d.pop("sl")
        pts = t.pnl_pts()
        d["pnl_pts"] = round(pts, 2)
        d["pnl_pct"] = round(100 * pts / t.entry - cost_pct, 3)
        d["pnl_rs"] = round(pts * qty - cost_pct / 100 * t.entry * qty, 2)
        rows.append(d)
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, "No trades in the backtest window."
    for col in ("setup_time", "entry_time", "t1_time", "exit_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    for col in ("entry", "stop", "target", "exit"):
        tl[col] = tl[col].round(2)
    wins, losses = tl[tl.pnl_pts > 0], tl[tl.pnl_pts <= 0]
    eq = tl["pnl_rs"].cumsum()
    gw, gl = wins.pnl_rs.sum(), -losses.pnl_rs.sum()
    lines = [
        f"Trades            : {len(tl)}  (CALL {sum(tl.side == 'CALL')}, PUT {sum(tl.side == 'PUT')})",
        f"Winners / Losers  : {len(wins)} / {len(losses)}  (win rate {100 * len(wins) / len(tl):.1f}%)",
        f"Reached 1:1 (T1)  : {sum(tl.t1_time != '-')}",
        f"Net P&L (points)  : {tl.pnl_pts.sum():+.2f} per share",
        f"Sum of trade %    : {tl.pnl_pct.sum():+.2f}%  (cost {cost_pct}% per trade)",
        f"Net P&L (Rs)      : {tl.pnl_rs.sum():+,.2f}  (qty {qty})",
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
    ap.add_argument("--interval", default="5m", choices=["5m", "2m"], help="candle timeframe")
    ap.add_argument("--csv", help="load OHLC from CSV instead of yfinance (same timeframe as --interval)")
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--one-at-a-time", action="store_true", help="no CALL/PUT overlap")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--cost-pct", type=float, default=0.0, help="round-trip cost in %% of entry")
    ap.add_argument("--day", help="print only this date's trades (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    global BAR_MIN
    BAR_MIN = int(a.interval[:-1])
    df = clean(load_csv(a.csv) if a.csv else fetch_yf(a.symbol, interval=a.interval))
    sessions = sorted(set(df.index.date))
    if not a.include_today and df.index[-1].time() < SQUARE_OFF:
        sessions = sessions[:-1]
        df = df[df.index.date <= sessions[-1]]
    window = sessions[-a.sessions:]
    df = add_indicators(df)
    trades = sorted(run(df, window[0], independent=not a.one_at_a_time),
                    key=lambda t: (t.entry_time, t.side))
    tl, summary = report(trades, a.qty, a.cost_pct)

    mode = "one trade at a time" if a.one_at_a_time else "CALL & PUT independent"
    header = (f"LAXIT ({mode}) | {a.symbol} {a.interval} | {window[0]} -> {window[-1]} ({len(window)} sessions)\n"
              f"SMA{sma_bands.LENGTH} High/Low, MACD {macd_ind.FAST}/{macd_ind.SLOW}/{macd_ind.SIGNAL}, crossover within "
              f"{CROSS_LOOKBACK} candles, entries {ENTRY_START:%H:%M}-{ENTRY_END:%H:%M}, "
              f"exit by {SQUARE_OFF:%H:%M}. P&L counts 50% at T1 + 50% at final exit.\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + summary + "\n")
    df[df.index.date >= window[0]].to_csv(os.path.join(a.out, "bars_with_indicators.csv"))

    print(header)
    show = tl if not a.day or tl.empty else tl[tl.entry_time.str[:10] == a.day]
    if not show.empty:
        print(show[["side", "setup_time", "entry_time", "entry", "stop", "target", "t1_time",
                    "exit_time", "exit", "reason", "pnl_pts"]].to_string(index=False))
    print("\n" + summary)


if __name__ == "__main__":
    main()

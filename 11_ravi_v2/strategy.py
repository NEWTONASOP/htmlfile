#!/usr/bin/env python3
"""
RAVI v2 - NIFTY 50 Multi-Window Range Breakout (client's Final Rule Card), ATM option buying, 5m.

Windows    : range = high/low of the NIFTY 5m candle(s):
               1 09:20 | 2 10:00 | 3 11:00 | 4 12:00 | 5 13:00 | 6 14:00 | 7 14:55 + 15:00 combined
             A window is active from the close of its (last) range candle until the next window's
             first range candle starts.
Signal     : at a 5m close, all true:
               NIFTY close above the active window's high (CE) / below its low (PE)
               ATM option (NIFTY close rounded to 50, nearest weekly expiry) premium:
                 above its VWAP (windows 1-4 only), above its EMA 20, ADX(14) >= 20
               that side not yet taken in this window (max 1 CE + 1 PE per window)
               daily limits not hit (max 6 trades, max loss Rs 10,000) and next open <= 15:15
Entry      : next 5m candle open of the option.
Reversal   : an opposite-side signal while in a trade closes it and opens the new side at the
             same next open (counts as the window's second trade). A same-side signal while
             already in that side is ignored. An open trade carries across windows.
Exits      : SL Rs 20 below entry; target Rs 50 above entry; trailing SL starts once the premium
             is +Rs 20 (high), then SL = highest premium - Rs 10, only up; square-off 15:20.
             Candle high/low, SL first, then target; fills at the level or the open if beyond.
Daily      : max trades/day 6, max daily loss Rs 10,000 (realised; no new trades once hit).

Usage (from the repository root):
    python 11_ravi_v2/strategy.py --download          # Angel One data (ANGEL_* env variables)
    python 11_ravi_v2/strategy.py                     # run on the cached data
    python 11_ravi_v2/strategy.py --day 2026-11-26
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import DATA_DIR, download, load_cached  # noqa: E402
from indicators.ema import ema  # noqa: E402
from indicators.vwap import vwap  # noqa: E402
from indicators.adx import adx  # noqa: E402

BAR = pd.Timedelta(minutes=5)
WINDOWS = [  # (label, range candle start times, VWAP filter)
    ("09:20", [time(9, 20)], True), ("10:00", [time(10, 0)], True), ("11:00", [time(11, 0)], True),
    ("12:00", [time(12, 0)], True), ("13:00", [time(13, 0)], False), ("14:00", [time(14, 0)], False),
    ("14:55", [time(14, 55), time(15, 0)], False),
]
STRIKE_STEP = 50
LOT_SIZE = 65
EXPIRY_WEEKDAY = 1               # Tuesday
# Settings (client's rule card defaults)
MAX_TRADES = 6
MAX_LOSS = 10_000.0
LAST_ENTRY = time(15, 15)
SQUARE_OFF = time(15, 20)        # close of the 15:15 candle
SL_RS = 20.0
TARGET_RS = 50.0
TRAIL_TRIGGER = 20.0
TRAIL_GAP = 10.0
EMA_LEN = 20
ADX_LEN = 14
ADX_MIN = 20.0


def atm(spot: float) -> int:
    return int(math.floor(spot / STRIKE_STEP + 0.5) * STRIKE_STEP)


def nearest_expiry(day: date, live: list[date]) -> date | None:
    """Nearest weekly expiry on or after `day` (the expiring contract on expiry day).
    None if Angel One no longer serves it (expired)."""
    tue = day + timedelta(days=(EXPIRY_WEEKDAY - day.weekday()) % 7)
    found = [e for e in live if tue - timedelta(days=6) < e <= tue and e >= day]
    return found[0] if found else None


def prepare(a):
    nifty = load_cached("nifty_5m")
    if nifty is None:
        raise SystemExit("No data: run with --download first (needs the ANGEL_* environment variables).")
    contracts = pd.read_csv(DATA_DIR / "contracts.csv", parse_dates=["expiry"])
    contracts["expiry"] = contracts.expiry.dt.date
    opts = {}
    for f in DATA_DIR.glob("opt_*.csv"):
        o = load_cached(f.stem)
        if o is None or o.empty:
            continue
        o["vwap"] = vwap(o)
        o["ema"] = ema(o, a.ema)
        o["adx"] = adx(o, a.adx_len, a.adx_len)
        opts[f.stem[4:]] = o
    return nifty, contracts, opts


@dataclass
class Trade:
    day: date
    window: str
    side: str
    symbol: str
    strike: int
    expiry: date
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    sl: float
    target: float
    best: float
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    sl_path: list = field(default_factory=list)

    @property
    def pnl(self) -> float:
        return self.exit - self.entry


def run_day(day, nb, opts, contracts, exp, a, checks):
    qty = a.lots * LOT_SIZE
    sym_of = {(r.strike, r.type): r.symbol for r in contracts[contracts.expiry == exp].itertuples()}
    strike_of = {r.symbol: int(r.strike) for r in contracts.itertuples()}
    idx = nb.index
    trades: list[Trade] = []
    pos: Trade | None = None
    pending = None                  # (symbol, side, signal ts, window dict)
    win = None                      # active window
    forming = None                  # window whose range candles are still forming
    n_day, pnl_day = 0, 0.0

    def close(ts, px, reason):
        nonlocal pos, pnl_day
        pos.exit_time, pos.exit, pos.reason = ts, float(px), reason
        trades.append(pos)
        pnl_day += pos.pnl * qty
        pos = None

    for i, ts in enumerate(idx):
        t = ts.time()
        end = (ts + BAR).time()
        last = i == len(idx) - 1

        # 1) pending signal: (reverse and) enter at this candle's open
        if pending is not None:
            sym, side, sig_ts, w = pending
            pending = None
            o = opts[sym]
            if ts in o.index:
                if pos is not None:                               # reversal
                    po = opts[pos.symbol]
                    close(ts, po.at[ts, "Open"] if ts in po.index else po.loc[:ts].Close.iloc[-1], "Reversal")
                px = float(o.at[ts, "Open"])
                pos = Trade(day, w["label"], side, sym, strike_of[sym], exp, sig_ts, ts, px,
                            px - a.sl, px + a.target, best=px)
                pos.sl_path.append((ts, pos.sl))
                w["taken"].add(side)
                n_day += 1

        # 2) manage the open trade on this option candle
        if pos is not None:
            o = opts[pos.symbol]
            if ts in o.index:
                ob = o.loc[ts]
                if ob.Low <= pos.sl:
                    close(ts, min(ob.Open, pos.sl), "StopLoss" if pos.sl <= pos.entry - a.sl + 1e-9 else "Trailing SL")
                elif ob.High >= pos.target:
                    close(ts, max(ob.Open, pos.target), "Target")
                else:
                    pos.best = max(pos.best, ob.High)
                    if pos.best - pos.entry >= a.trail_trigger - 1e-9:
                        new_sl = pos.best - a.trail_gap
                        if new_sl > pos.sl:
                            pos.sl = new_sl
                            pos.sl_path.append((ts, pos.sl))
                    if end >= a.square_off or last:
                        close(ts, ob.Close, "Square-off")
            elif end >= a.square_off or last:
                close(ts, float(o.loc[:ts].Close.iloc[-1]), "Square-off")
        if end > a.square_off:
            break

        # 3) windows: range candles
        w_here = next((w for w in WINDOWS if t in w[1]), None)
        if w_here is not None:
            if w_here[1][0] == t:                                  # first range candle: old window ends
                win = None
                forming = dict(label=w_here[0], hi=-math.inf, lo=math.inf, vwap=w_here[2], taken=set(),
                               last=w_here[1][-1])
            forming["hi"] = max(forming["hi"], float(nb.at[ts, "High"]))
            forming["lo"] = min(forming["lo"], float(nb.at[ts, "Low"]))
            if t == forming["last"]:
                win, forming = forming, None                      # active from this close on
            continue
        if win is None:
            continue

        # 4) signal check on this close
        c = float(nb.at[ts, "Close"])
        side = "CE" if c > win["hi"] else "PE" if c < win["lo"] else None
        if side is None or pending is not None:
            continue
        if pos is not None and pos.side == side:
            continue                                              # already in that side
        strike = atm(c)
        sym = sym_of.get((strike, side))
        row = dict(day=day, candle=ts, window=win["label"], side=side, nifty=c, strike=strike, symbol=sym,
                   in_trade=pos.side if pos else "")
        blockers = []
        if side in win["taken"]:
            blockers.append(f"{side} already taken in window")
        if n_day >= a.max_trades:
            blockers.append("max trades/day")
        if pnl_day <= -a.max_loss:
            blockers.append("max daily loss")
        if last or (ts + BAR).time() > a.last_entry:
            blockers.append("after last entry time")
        if sym is None or sym not in opts or ts not in opts[sym].index:
            blockers.append("no option data")
        else:
            ob = opts[sym].loc[ts]
            row.update(opt_close=ob.Close, vwap=ob.vwap, ema20=ob.ema, adx=ob.adx)
            if win["vwap"] and not ob.Close > ob.vwap:
                blockers.append("premium below VWAP")
            if not ob.Close > ob.ema:
                blockers.append(f"premium below EMA {a.ema}")
            if not ob.adx >= a.adx:
                blockers.append(f"ADX < {a.adx:g}")
        row["result"] = ("REVERSAL next open" if pos else "ENTRY next open") if not blockers else "; ".join(blockers)
        checks.append(row)
        if not blockers:
            pending = (sym, side, ts, win)
    if pos is not None:                                           # never overnight
        o = opts[pos.symbol]
        close(idx[-1], float(o.loc[:idx[-1]].Close.iloc[-1]), "Square-off")
    return trades


def report(trades, qty):
    tl = pd.DataFrame([dict(day=t.day, window=t.window, side=t.side, option=t.symbol, strike=t.strike,
                            expiry=t.expiry, signal=t.signal_time.strftime("%H:%M"),
                            entry_time=t.entry_time.strftime("%H:%M"), entry=round(t.entry, 2),
                            exit_time=t.exit_time.strftime("%H:%M"), exit=round(t.exit, 2), reason=t.reason,
                            pnl_pts=round(t.pnl, 2), pnl_rs=round(t.pnl * qty, 2),
                            sl_path=" > ".join(f"{a:%H:%M} {b:.2f}" for a, b in t.sl_path)) for t in trades])
    if tl.empty:
        return tl, ["No trades."]
    w = tl[tl.pnl_rs > 0]
    return tl, [
        f"Trades          : {len(tl)} (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})",
        f"Winners/losers  : {len(w)} / {len(tl) - len(w)}",
        f"Net P&L         : {tl.pnl_pts.sum():+.2f} premium points = Rs {tl.pnl_rs.sum():+,.2f} (qty {qty})",
        "Exit reasons    : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="refresh data from Angel One (ANGEL_* env vars)")
    ap.add_argument("--days", type=int, default=30, help="calendar days back to look for testable days")
    ap.add_argument("--max-trades", type=int, default=MAX_TRADES)
    ap.add_argument("--max-loss", type=float, default=MAX_LOSS, help="max daily loss in Rs")
    ap.add_argument("--last-entry", type=lambda s: time.fromisoformat(s), default=LAST_ENTRY)
    ap.add_argument("--square-off", type=lambda s: time.fromisoformat(s), default=SQUARE_OFF)
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--sl", type=float, default=SL_RS)
    ap.add_argument("--target", type=float, default=TARGET_RS)
    ap.add_argument("--trail-trigger", type=float, default=TRAIL_TRIGGER)
    ap.add_argument("--trail-gap", type=float, default=TRAIL_GAP)
    ap.add_argument("--ema", type=int, default=EMA_LEN)
    ap.add_argument("--adx-len", type=int, default=ADX_LEN)
    ap.add_argument("--adx", type=float, default=ADX_MIN, help="ADX threshold")
    ap.add_argument("--day", help="print only this date's trades (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    today = pd.Timestamp.now(tz="Asia/Kolkata").date()
    if a.download:
        from data import Angel
        live = sorted(set(Angel().nifty_options().expiry))
        cal = [today - timedelta(days=k) for k in range(a.days, -1, -1)]
        pairs = [(d, nearest_expiry(d, live)) for d in cal if d.weekday() < 5]
        pairs = [(d, e) for d, e in pairs if e is not None]
        print(f"Downloading NIFTY and options for {len(pairs)} candidate days ...")
        download(pairs, today - timedelta(days=a.days + 15), today)

    nifty, contracts, opts = prepare(a)
    live = sorted(set(contracts.expiry))
    tested, skipped, trades, checks = [], [], [], []
    for d in sorted(set(nifty.index.date)):
        if d < today - timedelta(days=a.days):
            continue
        nb = nifty[nifty.index.date == d]
        if (nb.index[-1] + BAR).time() < a.square_off:
            skipped.append((d, "session not finished"))
            continue
        exp = nearest_expiry(d, live)
        if exp is None:
            skipped.append((d, "expiry contract expired (Angel One has no data)"))
            continue
        tested.append((d, exp))
        trades += run_day(d, nb, opts, contracts, exp, a, checks)
    qty = a.lots * LOT_SIZE
    tl, lines = report(trades, qty)
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    pd.DataFrame(checks).to_csv(os.path.join(a.out, "checks.csv"), index=False)
    head = (f"RAVI v2 NIFTY multi-window range breakout | Angel One 5m | tested "
            f"{', '.join(f'{d:%d %b} (exp {e:%d %b})' for d, e in tested) or 'none'}\n"
            f"SL {a.sl:g}, target {a.target:g}, trail +{a.trail_trigger:g}/{a.trail_gap:g}, EMA {a.ema}, "
            f"ADX({a.adx_len}) >= {a.adx:g}, max {a.max_trades} trades/day, max loss Rs {a.max_loss:,.0f}, "
            f"entries to {a.last_entry:%H:%M}, square-off {a.square_off:%H:%M}, qty {qty}\n"
            f"Skipped: {len(skipped)} days ({', '.join(sorted(set(r for _, r in skipped)))})")
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(head + "\n\n" + "\n".join(lines) + "\n")
    print(head + "\n")
    show = tl if not a.day or tl.empty else tl[tl.day.astype(str) == a.day]
    if not show.empty:
        print(show[["day", "window", "side", "option", "signal", "entry_time", "entry", "exit_time", "exit",
                    "reason", "pnl_pts", "pnl_rs"]].to_string(index=False))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
RAVI v1 - NIFTY ORB (opening/hourly range breakout), ATM option buying, 5-minute candles.

Ranges     : high/low of the 5m candles starting 09:20, 10:00, 11:00, 12:00, 13:00, 14:00, 15:00.
             A range is active from its candle's close until the next range candle starts.
Breakout   : a NIFTY 5m candle CLOSES above the range high -> CE, below the range low -> PE
             (a touch does not count).
Confirm    : checked on every 5m close while NIFTY is still closed beyond the range, on the ATM
             option of that close (nearest 50 strike) of the chosen expiry:
               morning (09:20-12:00 ranges): option close > its session VWAP, NIFTY close above
                 (CE) / below (PE) its 9 EMA, option close > its 9 EMA, option ADX >= 20
               afternoon (13:00-15:00 ranges): option close > its 9 EMA (setting: 20),
                 NIFTY above/below its 9 EMA, option ADX >= 20  (no VWAP)
             Gap-day switch (--no-ema) drops the EMA checks (VWAP and ADX stay).
Entry      : option's next 5m candle open. Entries until the 15:15 candle open.
Exits      : SL Rs 20 below entry on the premium; trailing: every Rs 10 the premium's high gains
             moves the SL up Rs 10 (starts at once); target Rs 40 (OFF by default); 7 EMA exit:
             option 5m close below its 7 EMA -> exit at the next open; square-off 15:20.
             SL/target on candle high/low, SL first; SL fills at the level or the open if beyond.
Trades     : one at a time; max 2 per range (setting 1/2). The second trade in a range needs a
             fresh break: after a trade on one side, NIFTY must close back out of that side
             (inside or beyond the other side) before that side can trade again.
Day locks  : max trades, loss lock, profit lock (Rs, realised). OFF by default. Checked when a
             trade closes: no new entries for the rest of the day.
Expiry     : current = this week's expiry (on expiry day: next week's); next = the one after.

Usage (from the repository root):
    python 11_ravi_v1/strategy.py --download         # Angel One data (ANGEL_* env variables)
    python 11_ravi_v1/strategy.py                    # run on the cached data
    python 11_ravi_v1/strategy.py --adx 18 --pm-ema 20 --target --per-range 1 --lots 2
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
from data import DATA_DIR, download, load_cached  # noqa: E402
from indicators.ema import ema  # noqa: E402
from indicators.vwap import vwap  # noqa: E402
from indicators.adx import adx  # noqa: E402

BAR = pd.Timedelta(minutes=5)
RANGE_TIMES = [time(9, 20), time(10, 0), time(11, 0), time(12, 0), time(13, 0), time(14, 0), time(15, 0)]
AFTERNOON_FROM = time(13, 0)
LAST_ENTRY_OPEN = time(15, 15)
SQUARE_OFF = time(15, 20)        # close of the 15:15 candle
NIFTY_EMA = 9
MORNING_PM_EMA = 9
EXIT_EMA = 7
ADX_MIN = 20.0
SL_RS = 20.0
TARGET_RS = 40.0
TRAIL_STEP = 10.0                # every Rs 10 favourable ...
TRAIL_MOVE = 10.0                # ... moves the SL Rs 10
LOT_SIZE = 65
STRIKE_STEP = 50
EXPIRY_WEEKDAY = 1               # Tuesday


# ---------------------------------------------------------------- expiry / strike
def atm(spot: float) -> int:
    return int(math.floor(spot / STRIKE_STEP + 0.5) * STRIKE_STEP)


def choose_expiry(day: date, live: list[date], mode: str) -> date | None:
    """Weekly expiry the strategy trades on `day`; None if that contract is no longer served."""
    def week_expiry(tue: date) -> date:
        found = [e for e in live if tue - timedelta(days=6) < e <= tue]
        return found[0] if found else tue                 # expired: assume the Tuesday itself
    tue = day + timedelta(days=(EXPIRY_WEEKDAY - day.weekday()) % 7)
    weeks = [week_expiry(tue + timedelta(days=7 * k)) for k in range(4)]
    weeks = [e for e in weeks if e >= day]
    k = 1 if weeks[0] == day else 0                       # expiry day -> next week
    if mode == "next":
        k += 1
    exp = weeks[k]
    return exp if exp in live else None


# ---------------------------------------------------------------- data + indicators
def prepare(pm_ema: int):
    nifty = load_cached("nifty_5m")
    if nifty is None:
        raise SystemExit("No data: run with --download first (needs the ANGEL_* environment variables).")
    nifty["ema9"] = ema(nifty, NIFTY_EMA)
    contracts = pd.read_csv(DATA_DIR / "contracts.csv", parse_dates=["expiry"])
    contracts["expiry"] = contracts.expiry.dt.date
    opts = {}
    for f in DATA_DIR.glob("opt_*.csv"):
        sym = f.stem[4:]
        o = load_cached(f.stem)
        if o is None or o.empty:
            continue
        o["vwap"] = vwap(o)
        o["ema_m"] = ema(o, MORNING_PM_EMA)
        o["ema_a"] = ema(o, pm_ema)
        o["ema7"] = ema(o, EXIT_EMA)
        o["adx"] = adx(o)
        opts[sym] = o
    return nifty, contracts, opts


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    day: date
    range_time: str
    side: str                       # CE / PE
    symbol: str
    strike: int
    expiry: date
    signal_time: pd.Timestamp       # 5m close where all conditions were met
    entry_time: pd.Timestamp
    entry: float                    # option premium
    sl: float
    target: float | None
    best: float = 0.0
    exit_flag: bool = False         # 7 EMA close below -> exit at next open
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    sl_path: list = field(default_factory=list)

    @property
    def pnl(self) -> float:
        return self.exit - self.entry


def run_day(day, nb: pd.DataFrame, opts: dict, contracts: pd.DataFrame, exp: date, a, checks: list):
    qty = a.lots * LOT_SIZE
    sym_of = {(r.strike, r.type): r.symbol for r in contracts[contracts.expiry == exp].itertuples()}
    trades: list[Trade] = []
    pos: Trade | None = None
    pending = None
    rng = None
    n_day, pnl_day, locked = 0, 0.0, False
    idx = nb.index

    def close(ts, px, reason):
        nonlocal pos, n_day, pnl_day, locked
        pos.exit_time, pos.exit, pos.reason = ts, float(px), reason
        trades.append(pos)
        n_day += 1
        pnl_day += pos.pnl * qty
        if (a.max_trades and n_day >= a.max_trades) or (a.loss_lock and pnl_day <= -a.loss_lock) \
                or (a.profit_lock and pnl_day >= a.profit_lock):
            locked = True
        pos = None

    for i, ts in enumerate(idx):
        t = ts.time()
        end = (ts + BAR).time()
        last = i == len(idx) - 1

        # 1) pending entry at this candle's open
        if pending is not None:
            sym, side, sig_ts, rng_ref = pending
            pending = None
            o = opts[sym]
            if ts in o.index:
                px = float(o.at[ts, "Open"])
                k = next(r for r in contracts.itertuples() if r.symbol == sym)
                pos = Trade(day, rng_ref["label"], side, sym, int(k.strike), exp, sig_ts, ts, px,
                            px - SL_RS, px + TARGET_RS if a.target else None, best=px)
                pos.sl_path.append((ts, pos.sl))
                rng_ref["n"] += 1
                rng_ref["used"] = side

        # 2) manage the open trade on this candle (option candle)
        if pos is not None:
            o = opts[pos.symbol]
            if ts in o.index:
                ob = o.loc[ts]
                if pos.exit_flag:
                    close(ts, ob.Open, "7 EMA exit")
                elif ob.Low <= pos.sl:
                    close(ts, min(ob.Open, pos.sl), "StopLoss" if pos.sl < pos.entry - SL_RS + 1e-9
                          else "Trailing SL")
                elif pos.target is not None and ob.High >= pos.target:
                    close(ts, max(ob.Open, pos.target), "Target")
                else:
                    pos.best = max(pos.best, ob.High)
                    k = math.floor(round(pos.best - pos.entry, 6) / TRAIL_STEP)
                    new_sl = pos.entry - SL_RS + TRAIL_MOVE * max(k, 0)
                    if new_sl > pos.sl:
                        pos.sl = new_sl
                        pos.sl_path.append((ts, pos.sl))
                    if end >= SQUARE_OFF or last:
                        close(ts, ob.Close, "Square-off 15:20")
                    elif ob.Close < ob.ema7:
                        pos.exit_flag = True
            elif end >= SQUARE_OFF or last:                     # no option candle: exit at last price
                close(ts, float(o.loc[:ts].Close.iloc[-1]), "Square-off 15:20")
        if end > SQUARE_OFF:
            break

        # 3) a new range candle
        if t in RANGE_TIMES:
            rng = dict(label=t.strftime("%H:%M"), hi=float(nb.at[ts, "High"]), lo=float(nb.at[ts, "Low"]),
                       afternoon=t >= AFTERNOON_FROM, n=0, used=None)
            continue
        if rng is None:
            continue

        # 4) breakout state on this close
        c = float(nb.at[ts, "Close"])
        beyond = "CE" if c > rng["hi"] else "PE" if c < rng["lo"] else None
        if rng["used"] and beyond != rng["used"]:
            rng["used"] = None                                   # fresh break possible again
        if beyond is None or beyond == rng["used"] or pos is not None or pending is not None:
            continue

        # 5) confirmations on this close
        nxt_ok = not last and (ts + BAR).time() <= LAST_ENTRY_OPEN
        strike = atm(c)
        sym = sym_of.get((strike, beyond))
        row = dict(day=day, candle=ts, range=rng["label"], side=beyond, nifty=c, strike=strike, symbol=sym)
        blockers = []
        if locked:
            blockers.append("day locked")
        if rng["n"] >= a.per_range:
            blockers.append("range trades done")
        if not nxt_ok:
            blockers.append("after 15:15")
        if sym is None or sym not in opts or ts not in opts[sym].index:
            blockers.append("no option data")
        else:
            ob = opts[sym].loc[ts]
            ne = float(nb.at[ts, "ema9"])
            row.update(opt_close=ob.Close, vwap=ob.vwap, opt_ema=ob.ema_a if rng["afternoon"] else ob.ema_m,
                       nifty_ema9=ne, adx=ob.adx)
            if not rng["afternoon"] and not ob.Close > ob.vwap:
                blockers.append("premium below VWAP")
            if not a.no_ema:
                if not ((c > ne) if beyond == "CE" else (c < ne)):
                    blockers.append("NIFTY 9 EMA")
                pe = ob.ema_a if rng["afternoon"] else ob.ema_m
                if not ob.Close > pe:
                    blockers.append(f"premium below {a.pm_ema if rng['afternoon'] else MORNING_PM_EMA} EMA")
            if not ob.adx >= a.adx:
                blockers.append(f"ADX < {a.adx:g}")
        row["result"] = "ENTRY next open" if not blockers else "; ".join(blockers)
        checks.append(row)
        if not blockers:
            pending = (sym, beyond, ts, rng)
    if pos is not None:                                            # safety: never overnight
        o = opts[pos.symbol]
        close(idx[-1], float(o.loc[:idx[-1]].Close.iloc[-1]), "Square-off 15:20")
    return trades


def report(trades: list[Trade], qty: int):
    rows = [dict(day=t.day, range=t.range_time, side=t.side, option=t.symbol, strike=t.strike, expiry=t.expiry,
                 signal=t.signal_time.strftime("%H:%M"), entry_time=t.entry_time.strftime("%H:%M"),
                 entry=round(t.entry, 2), exit_time=t.exit_time.strftime("%H:%M"), exit=round(t.exit, 2),
                 reason=t.reason, pnl_pts=round(t.pnl, 2), pnl_rs=round(t.pnl * qty, 2),
                 sl_path=" > ".join(f"{a:%H:%M} {b:.2f}" for a, b in t.sl_path)) for t in trades]
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, ["No trades."]
    wins, losses = tl[tl.pnl_rs > 0], tl[tl.pnl_rs <= 0]
    lines = [
        f"Trades          : {len(tl)} (CE {sum(tl.side == 'CE')}, PE {sum(tl.side == 'PE')})",
        f"Winners/losers  : {len(wins)} / {len(losses)}",
        f"Net P&L         : {tl.pnl_pts.sum():+.2f} premium points = Rs {tl.pnl_rs.sum():+,.2f} (qty {qty})",
        "Exit reasons    : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    return tl, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="refresh data from Angel One (ANGEL_* env vars)")
    ap.add_argument("--days", type=int, default=30, help="calendar days back to look for testable days")
    ap.add_argument("--adx", type=float, default=ADX_MIN, help="ADX threshold")
    ap.add_argument("--pm-ema", type=int, choices=(9, 20), default=9, help="afternoon option-premium EMA")
    ap.add_argument("--target", action="store_true", help="use the Rs 40 target (default OFF)")
    ap.add_argument("--per-range", type=int, choices=(1, 2), default=2, help="trades per range")
    ap.add_argument("--no-ema", action="store_true", help="gap-day switch: no EMA confirmations")
    ap.add_argument("--expiry", choices=("current", "next"), default="current")
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--max-trades", type=int, default=0, help="daily trade lock (0 = off)")
    ap.add_argument("--loss-lock", type=float, default=0, help="daily loss lock in Rs (0 = off)")
    ap.add_argument("--profit-lock", type=float, default=0, help="daily profit lock in Rs (0 = off)")
    ap.add_argument("--day", help="print only this date's trades and checks (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    today = pd.Timestamp.now(tz="Asia/Kolkata").date()
    if a.download:
        from data import Angel
        live = sorted(set(Angel().nifty_options().expiry))
        cal = [today - timedelta(days=k) for k in range(a.days, -1, -1)]
        pairs = [(d, choose_expiry(d, live, a.expiry)) for d in cal if d.weekday() < 5]
        pairs = [(d, e) for d, e in pairs if e is not None]
        print(f"Downloading NIFTY and options for {len(pairs)} candidate days ...")
        download(pairs, today - timedelta(days=a.days + 15), today)

    nifty, contracts, opts = prepare(a.pm_ema)
    live = sorted(set(contracts.expiry))
    days = sorted(set(nifty.index.date))
    days = [d for d in days if d >= today - timedelta(days=a.days)]
    tested, skipped, trades, checks = [], [], [], []
    for d in days:
        nb = nifty[nifty.index.date == d]
        if (nb.index[-1] + BAR).time() < SQUARE_OFF:
            skipped.append((d, "session not finished"))
            continue
        exp = choose_expiry(d, live, a.expiry)
        if exp is None:
            skipped.append((d, "expiry contract expired (Angel One has no data)"))
            continue
        tested.append((d, exp))
        trades += run_day(d, nb, opts, contracts, exp, a, checks)
    qty = a.lots * LOT_SIZE
    tl, lines = report(trades, qty)
    ck = pd.DataFrame(checks)
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    ck.to_csv(os.path.join(a.out, "checks.csv"), index=False)
    head = (f"RAVI v1 NIFTY ORB | Angel One 5m | tested {', '.join(f'{d:%d %b} (exp {e:%d %b})' for d, e in tested)}\n"
            f"ADX >= {a.adx:g}, afternoon premium EMA {a.pm_ema}, target {'ON' if a.target else 'OFF'}, "
            f"{a.per_range}/range, EMA {'OFF (gap switch)' if a.no_ema else 'ON'}, expiry {a.expiry}, qty {qty}\n"
            f"Skipped: {len(skipped)} days ({', '.join(sorted(set(r for _, r in skipped)))})")
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(head + "\n\n" + "\n".join(lines) + "\n")
    print(head + "\n")
    show = tl if not a.day or tl.empty else tl[tl.day.astype(str) == a.day]
    if not show.empty:
        print(show[["day", "range", "side", "option", "signal", "entry_time", "entry", "exit_time", "exit",
                    "reason", "pnl_pts", "pnl_rs"]].to_string(index=False))
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()

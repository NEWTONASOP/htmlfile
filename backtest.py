#!/usr/bin/env python3
"""
Neeraj - Kyle Algo + Liquidity Swings strategy backtest (5-minute, NSE intraday).

Entries : Kyle Algo EMA ribbon (15 EMAs of HIGH, lengths 9..51 step 3).
          Fresh close above the whole ribbon -> CALL (long) next candle open.
          Fresh close below the whole ribbon -> PUT (short) next candle open.
          An opposite fresh signal while in a trade reverses the position.
Exits   : Liquidity Swings (LuxAlgo) confirmed zones, pivot lookback 14.
          CALL exits on the next confirmed swing-high (RED) zone,
          PUT exits on the next confirmed swing-low (GREEN) zone.
Stop    : fixed 1% from entry price (intrabar, on candle high/low).
Session : square off at 15:15 IST; no new entry from the candle ending 15:15.

Usage:
    python backtest.py                       # RELIANCE.NS via yfinance, last 5 sessions
    python backtest.py --sessions 5 --symbol RELIANCE.NS
    python backtest.py --csv data.csv        # use your own 5m OHLC (Datetime,Open,High,Low,Close)
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, asdict
from datetime import time

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"

# ---------------------------------------------------------------- settings
# Kyle Algo inputs as specified. NOTE: these four only drive the Supertrend
# BUY/SELL labels and candle colouring, which the strategy ignores. The EMA
# ribbon (the only part used) has no inputs. Kept here for documentation.
KYLE_SENSITIVITY = 1.7
KYLE_KELTNER_LEN = 11
KYLE_ATR_LEN = 10
KYLE_FACTOR = 1.0
RIBBON_LENGTHS = list(range(9, 52, 3))  # 9,12,...,51 -> 15 EMAs of high

# Liquidity Swings inputs. Swing Area / Filter only change how the zone box is
# drawn/hidden; with Count filter = 0 every confirmed pivot zone is shown, so
# every confirmed pivot is an exit event.
LS_PIVOT_LOOKBACK = 14
LS_SWING_AREA = "Wick Extremity"
LS_FILTER_BY = "Count"
LS_FILTER_VALUE = 0

STOP_LOSS_PCT = 1.0
SQUARE_OFF = time(15, 15)        # positions closed at 15:15 (close of 15:10 bar)
# No new trade on the candle ending 15:15 -> last entry fills at 15:05 open,
# so an entry signal candle must close by 15:05. Exit signals are acted on
# until the candle closing 15:10 (exit at 15:10 open).
LAST_ENTRY_SIGNAL_END = time(15, 5)
LAST_EXIT_SIGNAL_END = time(15, 10)


# ---------------------------------------------------------------- data
def fetch_yf(symbol: str, period: str = "60d", interval: str = "5m") -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(symbol, period=period, interval=interval, progress=False,
                     auto_adjust=False, multi_level_index=False)
    if df is None or df.empty:
        raise SystemExit(f"yfinance returned no data for {symbol}. "
                         "Check network access to query1/query2.finance.yahoo.com.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    tcol = next(c for c in df.columns if c.lower() in ("datetime", "date", "time", "timestamp"))
    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["Open", "High", "Low", "Close"]].dropna().copy()
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(IST)
    df.index = idx.tz_convert(IST)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    df = df[(t >= time(9, 15)) & (t <= time(15, 25))]  # regular NSE session, bar start times
    return df


# ---------------------------------------------------------------- indicators
def ema(s: pd.Series, n: int) -> pd.Series:
    # Pine ta.ema: alpha = 2/(n+1), recursive. Seed differences vanish after warm-up.
    return s.ewm(span=n, adjust=False).mean()


def pivots(high: np.ndarray, low: np.ndarray, L: int):
    """Pine-style ta.pivothigh/ta.pivotlow(L, L).

    Returns boolean arrays flagged on the CONFIRMATION bar (pivot bar + L),
    which is when Liquidity Swings draws the zone. Ties: pivot must be strictly
    beyond the left-side bars and at least equal to the right-side bars.
    """
    n = len(high)
    ph = np.zeros(n, bool)
    pl = np.zeros(n, bool)
    for t in range(2 * L, n):
        p = t - L
        h, lo = high[p], low[p]
        if h > high[p - L:p].max() and h >= high[p + 1:t + 1].max():
            ph[t] = True
        if lo < low[p - L:p].min() and lo <= low[p + 1:t + 1].min():
            pl[t] = True
    return ph, pl


def visible_zones(o, h, lo, c, conf, L: int, high_side: bool) -> dict:
    """Port of LuxAlgo Liquidity Swings get_counts/set_zone with Filter = Count.

    When a pivot confirms (bar j = pivot + L) its count resets to 0. On each later
    bar, the candle L bars back is counted if it trades inside the zone
    (low < top and high > btm). The zone box is only drawn when the count crosses
    above the filter value (0), i.e. when price first revisits the zone. If the
    next pivot of the same side confirms first, the zone is never drawn.
    Returns arrays: appear (box drawn on this bar), swing (flag on the pivot
    candle of a drawn zone), pivot_idx/top/btm (set on the appear bar).
    """
    n = len(h)
    appear, swing = np.zeros(n, bool), np.zeros(n, bool)
    pivot_idx = np.full(n, -1)
    top_a, btm_a = np.full(n, np.nan), np.full(n, np.nan)
    p = top = btm = None
    count = 0
    for j in range(n):
        if conf[j]:
            p, count = j - L, 0
            if high_side:   # Wick Extremity
                top, btm = h[p], max(o[p], c[p])
            else:
                top, btm = min(o[p], c[p]), lo[p]
            continue
        if p is None:
            continue
        k = j - L
        if lo[k] < top and h[k] > btm:
            count += 1
            if count == 1 and LS_FILTER_VALUE < 1:  # ta.crossover(count, filterValue=0)
                appear[j], swing[p] = True, True
                pivot_idx[j], top_a[j], btm_a[j] = p, top, btm
    return dict(appear=appear, swing=swing, pivot_idx=pivot_idx, top=top_a, btm=btm_a)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ribbon = pd.concat([ema(df["High"], n) for n in RIBBON_LENGTHS], axis=1)
    df["ribbon_top"] = ribbon.max(axis=1)
    df["ribbon_bot"] = ribbon.min(axis=1)
    above = df["Close"] > df["ribbon_top"]
    below = df["Close"] < df["ribbon_bot"]
    df["above"], df["below"] = above, below
    # fresh cross only: this candle fully above/below, previous candle was not
    df["call_sig"] = above & ~above.shift(1, fill_value=True)
    df["put_sig"] = below & ~below.shift(1, fill_value=True)

    L = LS_PIVOT_LOOKBACK
    o, h, lo, c = (df[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    ph, pl = pivots(h, lo, L)
    for color, conf in (("red", ph), ("green", pl)):
        z = visible_zones(o, h, lo, c, conf, L, high_side=(color == "red"))
        df[f"{color}_zone"] = z["appear"]    # zone box drawn on this candle (live)
        df[f"{color}_swing"] = z["swing"]    # swing candle of a zone that gets drawn (hindsight)
        df[f"{color}_pivot_time"] = pd.Series(z["pivot_idx"]).map(
            lambda k: df.index[int(k)] if k >= 0 else pd.NaT).to_numpy()
        df[f"{color}_top"], df[f"{color}_btm"] = z["top"], z["btm"]
    # warm-up: need the slowest EMA and the pivot window to be meaningful
    df["warm"] = np.arange(len(df)) >= max(3 * max(RIBBON_LENGTHS), 2 * L)
    return df


# ---------------------------------------------------------------- backtest
@dataclass
class Trade:
    side: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    stop: float
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    zone_pivot_time: pd.Timestamp | None = None

    @property
    def pnl_pts(self):
        d = 1 if self.side == "CALL" else -1
        return d * (self.exit - self.entry)

    @property
    def pnl_pct(self):
        return 100 * self.pnl_pts / self.entry


def run(df: pd.DataFrame, start_date, reverse: bool = True, exit_at: str = "swing",
        sides: tuple = ("CALL", "PUT")) -> list[Trade]:
    """exit_at="swing":   exit at the close of the zone's swing candle (as read on a
                          finished chart; uses the next 14 candles = hindsight).
       exit_at="confirm": exit at the next open after the zone appears live."""
    trades: list[Trade] = []
    pos: Trade | None = None
    pending = None  # dict(exit_reason=str|None, enter=str|None, signal_time, zone_time)
    sl = STOP_LOSS_PCT / 100
    idx = df.index
    dates = idx.date
    n = len(df)

    def close_pos(t, px, reason, zone_time=None):
        nonlocal pos
        pos.exit_time, pos.exit, pos.reason = t, float(px), reason
        pos.zone_pivot_time = zone_time
        trades.append(pos)
        pos = None

    for i in range(n):
        ts = idx[i]
        o, h, lo, c = (df.iat[i, df.columns.get_loc(k)] for k in ("Open", "High", "Low", "Close"))
        bar_end = (ts + pd.Timedelta(minutes=5)).time()
        in_window = dates[i] >= start_date
        last_bar_of_day = i == n - 1 or dates[i + 1] != dates[i]

        # 1) orders decided at previous close fill at this bar's open (same day only)
        if pending is not None and i > 0 and dates[i - 1] == dates[i] and bar_end <= SQUARE_OFF:
            if pending["exit_reason"] and pos is not None:
                close_pos(ts, o, pending["exit_reason"], pending.get("zone_time"))
            if pending["enter"] and pos is None:
                stop = o * (1 - sl) if pending["enter"] == "CALL" else o * (1 + sl)
                pos = Trade(pending["enter"], pending["signal_time"], ts, float(o), float(stop))
        pending = None

        # 2) stop loss, intrabar
        if pos is not None:
            if pos.side == "CALL" and lo <= pos.stop:
                close_pos(ts, min(o, pos.stop), "StopLoss")
            elif pos.side == "PUT" and h >= pos.stop:
                close_pos(ts, max(o, pos.stop), "StopLoss")

        # 3) square off at 15:15 (close of the 15:10 candle) or last bar of the day
        if pos is not None and (bar_end >= SQUARE_OFF or last_bar_of_day):
            close_pos(ts, c, "SquareOff 15:15")

        # 4) evaluate signals at this candle's close
        if not (in_window and df["warm"].iat[i]) or bar_end > LAST_EXIT_SIGNAL_END or last_bar_of_day:
            continue
        exit_reason, zone_time, enter = None, None, None
        call_sig = df["call_sig"].iat[i] and "CALL" in sides
        put_sig = df["put_sig"].iat[i] and "PUT" in sides
        if bar_end > LAST_ENTRY_SIGNAL_END:
            call_sig = put_sig = False  # too late for a new trade (or a reversal)
        if pos is not None and exit_at == "swing":
            side = pos.side
            if (side == "CALL" and df["red_swing"].iat[i]) or (side == "PUT" and df["green_swing"].iat[i]):
                name = "RED" if side == "CALL" else "GREEN"
                close_pos(ts, c, f"{name} zone (swing candle)", ts)
                if side == "CALL":
                    call_sig = False  # don't exit and immediately re-enter the same side
                else:
                    put_sig = False
        if pos is not None:
            if exit_at == "confirm" and pos.side == "CALL" and df["red_zone"].iat[i]:
                exit_reason, zone_time = "RED liquidity zone", df["red_pivot_time"].iat[i]
            elif exit_at == "confirm" and pos.side == "PUT" and df["green_zone"].iat[i]:
                exit_reason, zone_time = "GREEN liquidity zone", df["green_pivot_time"].iat[i]
            if reverse and pos.side == "CALL" and put_sig:
                exit_reason = exit_reason or "Reverse (PUT signal)"
                enter = "PUT"
            elif reverse and pos.side == "PUT" and call_sig:
                exit_reason = exit_reason or "Reverse (CALL signal)"
                enter = "CALL"
            elif exit_reason:
                # flat after the exit: a fresh same-bar signal may still enter
                enter = "CALL" if call_sig else "PUT" if put_sig else None
                if enter == pos.side:
                    enter = None  # don't exit and immediately re-enter the same side
        else:
            enter = "CALL" if call_sig else "PUT" if put_sig else None
        if exit_reason or enter:
            pending = dict(exit_reason=exit_reason, enter=enter, signal_time=ts, zone_time=zone_time)

    if pos is not None:  # data ended mid-trade
        close_pos(idx[-1], df["Close"].iat[-1], "End of data")
    return trades


# ---------------------------------------------------------------- reporting
def report(trades: list[Trade], qty: int, cost_pct: float) -> tuple[pd.DataFrame, str]:
    rows = []
    for t in trades:
        d = asdict(t)
        d["pnl_pts"] = round(t.pnl_pts, 2)
        d["pnl_pct"] = round(t.pnl_pct, 3)
        d["net_pnl_pct"] = round(t.pnl_pct - cost_pct, 3)
        d["pnl_rs"] = round(t.pnl_pts * qty - cost_pct / 100 * t.entry * qty, 2)
        rows.append(d)
    tl = pd.DataFrame(rows)
    if tl.empty:
        return tl, "No trades in the backtest window."
    for col in ("signal_time", "entry_time", "exit_time", "zone_pivot_time"):
        tl[col] = pd.to_datetime(tl[col]).dt.strftime("%Y-%m-%d %H:%M")
    tl["entry"] = tl["entry"].round(2)
    tl["stop"] = tl["stop"].round(2)
    tl["exit"] = tl["exit"].round(2)

    wins = tl[tl.pnl_pts > 0]
    losses = tl[tl.pnl_pts <= 0]
    eq = tl["pnl_rs"].cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min()
    gross_win, gross_loss = wins.pnl_rs.sum(), -losses.pnl_rs.sum()
    lines = [
        f"Trades            : {len(tl)}  (CALL {sum(tl.side == 'CALL')}, PUT {sum(tl.side == 'PUT')})",
        f"Winners / Losers  : {len(wins)} / {len(losses)}  (win rate {100 * len(wins) / len(tl):.1f}%)",
        f"Net P&L (points)  : {tl.pnl_pts.sum():+.2f} per share",
        f"Sum of trade %    : {tl.net_pnl_pct.sum():+.2f}%  (cost {cost_pct}% per round trip)",
        f"Net P&L (Rs)      : {tl.pnl_rs.sum():+,.2f}  (qty {qty})",
        f"Avg win / loss    : {wins.pnl_rs.mean() if len(wins) else 0:+,.2f} / "
        f"{losses.pnl_rs.mean() if len(losses) else 0:+,.2f} Rs",
        f"Profit factor     : {gross_win / gross_loss:.2f}" if gross_loss > 0 else "Profit factor     : inf",
        f"Max drawdown (Rs) : {dd:,.2f}",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
        "",
        "Per day (Rs):",
    ]
    per_day = tl.groupby(tl.entry_time.str[:10]).agg(trades=("pnl_rs", "size"), pnl_rs=("pnl_rs", "sum"))
    lines += [f"  {d}: {int(r.trades):2d} trades  {r.pnl_rs:+,.2f}" for d, r in per_day.iterrows()]
    return tl, "\n".join(lines)


def list_zones(df: pd.DataFrame, day) -> None:
    """Print every zone box drawn on `day`: where it starts and when it appears."""
    d = df[df.index.date == day]
    print(f"Liquidity Swings zones drawn on {day} (lookback {LS_PIVOT_LOOKBACK}, Count filter {LS_FILTER_VALUE})")
    for ts, r in d.iterrows():
        for color in ("red", "green"):
            if r[f"{color}_zone"]:
                print(f"{color.upper():5} zone: box starts {r[f'{color}_pivot_time']:%Y-%m-%d %H:%M} | "
                      f"appears {ts:%H:%M} | {r[f'{color}_btm']:.2f}-{r[f'{color}_top']:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="RELIANCE.NS")
    ap.add_argument("--csv", help="load 5m OHLC from CSV instead of yfinance")
    ap.add_argument("--sessions", type=int, default=5, help="trading sessions to backtest (5 = one week)")
    ap.add_argument("--include-today", action="store_true", help="include an incomplete current session")
    ap.add_argument("--qty", type=int, default=1, help="shares per trade for Rs P&L")
    ap.add_argument("--cost-pct", type=float, default=0.0, help="round-trip cost in %% of entry")
    ap.add_argument("--exit-at", choices=["swing", "confirm"], default="swing",
                    help="swing (default): exit at the zone's swing candle, like reading a "
                         "finished chart (hindsight). confirm: exit when the zone appears live")
    ap.add_argument("--mode", choices=["independent", "reverse", "hold"], default="independent",
                    help="independent (default): CALL and PUT are separate trades that can be open "
                         "together, each closed only by its own zone, SL or 15:15. reverse: one "
                         "position, an opposite signal reverses it. hold: one position, opposite "
                         "signals ignored until it closes")
    ap.add_argument("--no-reverse", action="store_true", help="same as --mode hold")
    ap.add_argument("--zones", metavar="YYYY-MM-DD",
                    help="only list the Liquidity Swings zones drawn on that date, then exit")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    raw = load_csv(a.csv) if a.csv else fetch_yf(a.symbol)
    df = clean(raw)
    sessions = sorted(set(df.index.date))
    if not a.include_today and df.index[-1].time() < time(15, 25):
        sessions = sessions[:-1]  # drop the incomplete live session
        df = df[df.index.date <= sessions[-1]]
    window = sessions[-a.sessions:]
    df = add_indicators(df)
    if a.zones:
        list_zones(df, pd.Timestamp(a.zones).date())
        return
    if a.no_reverse:
        a.mode = "hold"
    if a.mode == "independent":
        trades = (run(df, window[0], reverse=False, exit_at=a.exit_at, sides=("CALL",))
                  + run(df, window[0], reverse=False, exit_at=a.exit_at, sides=("PUT",)))
        trades.sort(key=lambda t: (t.entry_time, t.side))
    else:
        trades = run(df, window[0], reverse=a.mode == "reverse", exit_at=a.exit_at)
    tl, summary = report(trades, a.qty, a.cost_pct)

    mode = {"independent": "CALL & PUT independent", "reverse": "reverse on opposite signal",
            "hold": "one trade at a time, hold through opposite signals"}[a.mode]
    mode += (", exit at swing candle [hindsight]" if a.exit_at == "swing"
             else ", exit when zone appears [live]")
    header = (f"Kyle Algo ribbon + Liquidity Swings ({mode}) | {a.symbol} 5m | "
              f"{window[0]} -> {window[-1]} ({len(window)} sessions)\n"
              f"Warm-up history: {sessions[0]} onward ({len(df)} bars). SL {STOP_LOSS_PCT}%, "
              f"pivot lookback {LS_PIVOT_LOOKBACK}, square-off {SQUARE_OFF:%H:%M} IST\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + summary + "\n")
    df[df.index.date >= window[0]].to_csv(os.path.join(a.out, "bars_with_indicators.csv"))
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print(header)
    if not tl.empty:
        print(tl[["side", "signal_time", "entry_time", "entry", "stop", "exit_time", "exit",
                  "reason", "pnl_pts", "pnl_pct"]].to_string(index=False))
    print("\n" + summary)


if __name__ == "__main__":
    main()

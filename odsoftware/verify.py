#!/usr/bin/env python3
"""
Checks the Python rebuild of OD SOFTWARE against TradingView's own output.

Input: the CSV written by tv_download/download.mjs (candles + the script's plots).
Compares, after warm-up:
  * SMA 40 vs the script's "Trend MA line"
  * DEMA 20 vs the script's "Fast MA"
  * Python BUY/SELL arrows vs the script's arrows (every candle)
With --yahoo, also rebuilds the arrows from yfinance 1-minute data (^NSEI -> 3m) and reports
how many TradingView arrows the Yahoo prices reproduce on the dates both cover.

Usage (from the repository root):
    python odsoftware/verify.py odsoftware/data/NSE_NIFTY_3.csv
    python odsoftware/verify.py odsoftware/data/NSE_NIFTY_3.csv --yahoo
    python odsoftware/verify.py odsoftware/data/NSE_RELIANCE_3.csv --yahoo --symbol RELIANCE.NS
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import IST, fetch_1m, load_csv, clean, to_timeframe  # noqa: E402
from strategy import add_indicators, TIMEFRAME_MIN  # noqa: E402
from indicators.atr_trail import atr_trail  # noqa: E402


def load_tv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.index = pd.to_datetime(df.pop("Datetime")).dt.tz_convert(IST)
    return df


def arrows(df: pd.DataFrame) -> pd.Series:
    return pd.Series(np.where(df.buy_arrow, "BUY", np.where(df.sell_arrow, "SELL", "")), index=df.index)


def replay_script(df: pd.DataFrame, sl: float = 10, tp: float = 20) -> list[tuple]:
    """The script's own Strategy Tester (default inputs), to compare with its trade list.

    Entry at the next open after an ATR-trail flip; one position; an opposite flip reverses it;
    exits at entry -/+ sl / tp points (Trade Mode "Point"), active from the candle after entry;
    when one candle touches both, TradingView's path rule (open -> nearer extreme first).
    No session rules. Returns (entry_time, side, exit_time or None, kind).
    """
    sig = atr_trail(df)
    O, H, L = (df[k].to_numpy() for k in ("Open", "High", "Low"))
    buy, sell = sig.trail_buy.to_numpy(), sig.trail_sell.to_numpy()
    t = df.index
    out, pos, pend = [], None, None
    for i in range(len(df)):
        if pend is not None:
            if pos is not None and pos[1] != pend:
                out.append((t[pos[0]], pos[1], t[i], "reverse"))
                pos = None
            if pos is None:
                pos = (i, pend, O[i])
            pend = None
        if pos is not None and pos[0] < i:
            k, side, e = pos
            stop, tgt = (e - sl, e + tp) if side == "LONG" else (e + sl, e - tp)
            hs = L[i] <= stop if side == "LONG" else H[i] >= stop
            ht = H[i] >= tgt if side == "LONG" else L[i] <= tgt
            if hs and ht:
                high_first = abs(H[i] - O[i]) < abs(L[i] - O[i])
                ht = high_first if side == "LONG" else not high_first
                hs = not ht
            if hs or ht:
                out.append((t[k], side, t[i], "SL" if hs else "Profit"))
                pos = None
        if buy[i]:
            pend = "LONG"
        elif sell[i]:
            pend = "SHORT"
    if pos is not None:
        out.append((t[pos[0]], pos[1], None, "open"))
    return out


def compare_tv_trades(df: pd.DataFrame, path: str):
    tvt = pd.read_csv(path)
    kind = {"Long SL": "SL", "Short SL": "SL", "Long Profit": "Profit", "Short Profit": "Profit",
            "Long": "reverse", "Short": "reverse"}
    rows = []
    for r in tvt.itertuples():
        if r.reason == "Margin call":              # TradingView partial close from position sizing
            continue
        et = pd.Timestamp(r.entry_time).tz_convert(IST)
        k = kind.get(r.reason, "open") if isinstance(r.reason, str) else "open"
        xt = None if k == "open" else pd.Timestamp(r.exit_time).tz_convert(IST)
        rows.append((et, r.side, xt, k))
    tv_set, py = set(rows), replay_script(df)
    py_set = set(py)
    same = len(tv_set & py_set)
    print(f"Script trades (ATR-trail entries, 10/20-pt exits, reversals): TradingView {len(tv_set)} "
          f"(+{len(tvt) - len(rows)} margin-call rows skipped), Python replay {len(py_set)}, "
          f"identical entry+exit {same}")
    for et, side, xt, k in sorted(tv_set ^ py_set, key=lambda x: x[0])[:10]:
        who = "TV only" if (et, side, xt, k) in tv_set else "Python only"
        print(f"  {who:11} {et:%Y-%m-%d %H:%M} {side:5} -> {xt:%Y-%m-%d %H:%M} {k}" if xt is not None
              else f"  {who:11} {et:%Y-%m-%d %H:%M} {side:5} -> open")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--yahoo", action="store_true", help="also compare arrows built from yfinance data")
    ap.add_argument("--symbol", default="^NSEI", help="yfinance symbol for --yahoo (e.g. RELIANCE.NS)")
    a = ap.parse_args()

    tv = load_tv(a.csv)
    # same data path as `strategy.py --csv`
    py = add_indicators(to_timeframe(clean(load_csv(a.csv)), TIMEFRAME_MIN))
    if not py.index.equals(tv.index):
        print(f"note: strategy data path keeps {len(py)} of {len(tv)} TradingView candles")
        tv = tv.loc[py.index]
    w = py["warm"].to_numpy()
    print(f"{a.csv}: {len(tv)} candles {tv.index[0]:%Y-%m-%d %H:%M} -> {tv.index[-1]:%Y-%m-%d %H:%M}, "
          f"checked from candle {int(np.argmax(w))} (warm-up)")

    d_slow = (py["sma40"] - tv["TV_SlowMA"])[w].abs()
    d_fast = (py["dema20"] - tv["TV_FastMA"])[w].abs()
    print(f"SMA 40  vs TV Trend MA line : max diff {d_slow.max():.6f}, mean {d_slow.mean():.6f}")
    print(f"DEMA 20 vs TV Fast MA       : max diff {d_fast.max():.6f}, mean {d_fast.mean():.6f}")

    tv_arrow = pd.Series(np.where(tv.TV_BuyArrow == 1, "BUY", np.where(tv.TV_SellArrow == 1, "SELL", "")),
                         index=tv.index)[w]
    py_arrow = arrows(py)[w]
    n_tv = int((tv_arrow != "").sum())
    same = int(((tv_arrow == py_arrow) & (tv_arrow != "")).sum())
    diff = tv_arrow != py_arrow
    print(f"Arrows: TradingView {n_tv} ({(tv_arrow == 'BUY').sum()} BUY, {(tv_arrow == 'SELL').sum()} SELL), "
          f"Python reproduces {same}, candles that differ {int(diff.sum())}")
    for ts in tv_arrow.index[diff][:20]:
        print(f"  {ts:%Y-%m-%d %H:%M}  TV={tv_arrow[ts] or '-':4}  Python={py_arrow[ts] or '-'}")

    trades_csv = a.csv[:-4] + "_tv_trades.csv"
    if Path(trades_csv).exists():
        compare_tv_trades(py, trades_csv)

    if a.yahoo:
        yh = add_indicators(to_timeframe(clean(fetch_1m(a.symbol, days=30)), TIMEFRAME_MIN))
        yh = yh[yh["warm"]]
        both = tv_arrow.index.intersection(yh.index)
        if len(both) == 0:
            print("Yahoo: no overlapping candles with the TradingView file.")
            return
        ta, ya = tv_arrow[both], arrows(yh).loc[both]
        days = sorted(set(both.date))
        n = int((ta != "").sum())
        hit = int(((ta == ya) & (ta != "")).sum())
        print(f"Yahoo {a.symbol} 1m->3m vs TradingView, {days[0]} -> {days[-1]} ({len(days)} sessions, "
              f"{len(both)} candles): TV arrows {n}, same candle and side on Yahoo {hit}, "
              f"Yahoo-only arrows {int(((ya != '') & (ta == '')).sum())}")
        dd = ta != ya
        for ts in ta.index[dd][:20]:
            print(f"  {ts:%Y-%m-%d %H:%M}  TV={ta[ts] or '-':4}  Yahoo={ya[ts] or '-'}")


if __name__ == "__main__":
    main()

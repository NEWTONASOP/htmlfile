#!/usr/bin/env python3
"""
OD SOFTWARE on a basket of NSE stocks with a fixed capital (Yahoo data).

Each stock gets an equal share of the capital (no compounding): every trade buys/sells as many
shares as that share allows at the entry price. Rules are exactly those of strategy.py (the
script's signal, stop = closer of 10 points / 1%, trailing after +20 points, reverse, held
overnight). Shorts are held overnight, which means stock futures in practice, so charges use
NSE stock-futures rates (approximate; see CHARGES).

Usage (from the repository root):
    python odsoftware/portfolio.py                          # 10 largest NIFTY stocks, Rs 1,00,000
    python odsoftware/portfolio.py --capital 500000 --symbols TCS.NS INFY.NS
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # this strategy folder only
from data import fetch_1m  # noqa: E402
from strategy import prepare, run  # noqa: E402

STOCKS = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "BHARTIARTL.NS",
          "TCS.NS", "LT.NS", "ITC.NS", "SBIN.NS", "KOTAKBANK.NS"]
CAPITAL = 100_000

# NSE stock futures, discount-broker rates (approximate, check your broker's calculator)
CHARGES = dict(
    brokerage_pct=0.03, brokerage_max=20.0,   # per order: 0.03% or Rs 20, whichever is lower
    stt_sell_pct=0.02,                        # STT on the sell side
    exchange_pct=0.00173,                     # NSE transaction charge, both sides
    sebi_per_crore=10.0,                      # SEBI fee, both sides
    stamp_buy_pct=0.002,                      # stamp duty on the buy side
    gst_pct=18.0,                             # GST on brokerage + exchange + SEBI
)


def charges(buy_value: float, sell_value: float, c: dict = CHARGES) -> float:
    turnover = buy_value + sell_value
    brokerage = sum(min(c["brokerage_max"], c["brokerage_pct"] / 100 * v) for v in (buy_value, sell_value))
    stt = c["stt_sell_pct"] / 100 * sell_value
    exchange = c["exchange_pct"] / 100 * turnover
    sebi = c["sebi_per_crore"] / 1e7 * turnover
    stamp = c["stamp_buy_pct"] / 100 * buy_value
    gst = c["gst_pct"] / 100 * (brokerage + exchange + sebi)
    return brokerage + stt + exchange + sebi + stamp + gst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="+", default=STOCKS)
    ap.add_argument("--capital", type=float, default=CAPITAL)
    ap.add_argument("--sessions", type=int, default=20, help="trading sessions (Yahoo: max ~20)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    alloc = a.capital / len(a.symbols)
    rows, windows = [], []
    for sym in a.symbols:
        df, window = prepare(fetch_1m(sym, days=30), a.sessions)
        windows.append((window[0], window[-1], len(window)))
        for t in run(df, window[0]):
            qty = math.floor(alloc / t.entry)
            if qty == 0:
                continue
            entry_v, exit_v = t.entry * qty, t.exit * qty
            buy_v, sell_v = (entry_v, exit_v) if t.side == "BUY" else (exit_v, entry_v)
            gross = t.pnl_pts * qty
            ch = charges(buy_v, sell_v)
            rows.append(dict(symbol=sym.replace(".NS", ""), side=t.side, entry_time=t.entry_time,
                             entry=round(t.entry, 2), exit_time=t.exit_time, exit=round(t.exit, 2),
                             reason=t.reason, qty=qty, gross=round(gross, 2), charges=round(ch, 2),
                             net=round(gross - ch, 2)))
    tl = pd.DataFrame(rows).sort_values("exit_time").reset_index(drop=True)

    per = tl.groupby("symbol", sort=False).agg(
        trades=("net", "size"), wins=("net", lambda s: int((s > 0).sum())),
        gross=("gross", "sum"), charges=("charges", "sum"), net=("net", "sum"))
    per = per.reindex([s.replace(".NS", "") for s in a.symbols]).fillna(0)
    per["win%"] = (100 * per.wins / per.trades).round(1)
    eq = tl.net.cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min()
    w0 = min(w[0] for w in windows)
    w1 = max(w[1] for w in windows)
    n = max(w[2] for w in windows)
    tot = per[["trades", "wins", "gross", "charges", "net"]].sum()
    lines = [
        f"OD SOFTWARE basket | {len(a.symbols)} stocks, Yahoo 1m -> 3m | {w0} -> {w1} ({n} sessions)",
        f"Capital Rs {a.capital:,.0f}, Rs {alloc:,.0f} per stock, no compounding, "
        f"NSE stock-futures charges (approximate)",
        "",
        per.assign(gross=per.gross.round(0), charges=per.charges.round(0), net=per.net.round(0))
           .astype({"trades": int, "wins": int}).to_string(),
        "",
        f"Trades            : {int(tot.trades)} (winning {int(tot.wins)}, {100 * tot.wins / tot.trades:.1f}%)",
        f"Gross P&L         : Rs {tot.gross:+,.0f}",
        f"Charges           : Rs {tot.charges:,.0f}",
        f"Net P&L           : Rs {tot.net:+,.0f}  ({100 * tot.net / a.capital:+.2f}% of capital)",
        f"Max drawdown      : Rs {dd:,.0f} (closed trades, all stocks together)",
        "Exit reasons      : " + ", ".join(f"{k}={v}" for k, v in tl.reason.value_counts().items()),
    ]
    os.makedirs(a.out, exist_ok=True)
    tl.assign(entry_time=tl.entry_time.dt.strftime("%Y-%m-%d %H:%M"),
              exit_time=tl.exit_time.dt.strftime("%Y-%m-%d %H:%M")).to_csv(
        os.path.join(a.out, "portfolio_trades.csv"), index=False)
    with open(os.path.join(a.out, "portfolio_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

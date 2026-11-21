#!/usr/bin/env python3
"""
PRAFUL - ICT Session Scalper signals on gold, 5-minute candles.

Signals : ▲ LONG / ▼ SHORT from the ICT Session Scalper Toolkit (indicators/ict_scalper.py):
          liquidity sweep -> displacement -> FVG tap / IFVG, inside the London or New York
          killzone (New York time), stop beyond the sweep capped at 3 x ATR14 (else skipped).
Trades  : every A+ or B signal opens its own trade (multiple entries allowed) at the signal
          candle's close; 0.01 lot = 1 ounce, so $1 of gold movement = $1.
Exits   : whichever comes first, checked candle by candle from the next candle
          1. stop loss: the indicator's SL                      (checked first)
          2. take profit: +$3 of price movement
          3. cross: a liquidity sweep ✗ in the trade's direction
             (above price for a BUY, below price for a SELL), at the swept level
Cost    : $0.30 spread per trade.
Data    : COMEX gold futures GC=F (Yahoo has no spot XAUUSD), SMT vs silver SI=F,
          about the last 60 days of 5-minute candles.

Usage:
    python praful/strategy.py
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
from data import fetch  # noqa: E402
from indicators.ict_scalper import run as ict_run  # noqa: E402

SYMBOL = "GC=F"
SMT_SYMBOL = "SI=F"
MINTICK = 0.10            # GC tick
TP_USD = 3.0              # +$3 per trade at 0.01 lot = $3 of price movement
OZ = 1.0                  # 0.01 lot = 1 ounce
SPREAD = 0.30
TRADE_GRADES = ("A+", "B")


def simulate(bars: pd.DataFrame, sig: dict) -> dict:
    O, H, L = bars.Open.to_numpy(), bars.High.to_numpy(), bars.Low.to_numpy()
    SB, SS = bars.swept_buyside.to_numpy(), bars.swept_sellside.to_numpy()
    buy = sig["side"] == "BUY"
    e, sl = sig["entry"], sig["sl"]
    tp = e + TP_USD / OZ if buy else e - TP_USD / OZ
    for j in range(sig["i"] + 1, len(bars)):
        if (L[j] <= sl) if buy else (H[j] >= sl):
            return dict(exit_i=j, exit=min(O[j], sl) if buy else max(O[j], sl), reason="StopLoss")
        hits = []
        if (H[j] >= tp) if buy else (L[j] <= tp):
            hits.append((max(O[j], tp) if buy else min(O[j], tp), "Target +$3"))
        cross = SB[j] if buy else SS[j]
        if cross:
            lvl = min(cross) if buy else max(cross)        # first level reached
            hits.append((max(O[j], lvl) if buy else min(O[j], lvl), "Cross ✗"))
        if hits:
            px, why = (min(hits) if buy else max(hits))     # the first one price reaches
            return dict(exit_i=j, exit=px, reason=why)
    return dict(exit_i=len(bars) - 1, exit=float(bars.Close.iloc[-1]), reason="Open at end of data")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()

    gold = fetch(SYMBOL)
    try:
        silver = fetch(SMT_SYMBOL)
    except SystemExit:
        silver = None
    bars, signals = ict_run(gold, silver, MINTICK)

    rows = []
    for s in signals:
        if s["skipped"]:
            continue
        r = simulate(bars, s)
        pnl = (r["exit"] - s["entry"]) * OZ if s["side"] == "BUY" else (s["entry"] - r["exit"]) * OZ
        rows.append(dict(time=s["time"].strftime("%Y-%m-%d %H:%M"), side=s["side"], grade=s["grade"],
                         entry=round(s["entry"], 2), sl=round(s["sl"], 2),
                         exit_time=bars.index[r["exit_i"]].strftime("%Y-%m-%d %H:%M"),
                         exit=round(r["exit"], 2), reason=r["reason"],
                         pnl_usd=round(pnl - SPREAD, 2), traded=s["grade"] in TRADE_GRADES))
    tl = pd.DataFrame(rows)
    skipped = sum(s["skipped"] for s in signals)

    def stats(t: pd.DataFrame, name: str) -> list[str]:
        if t.empty:
            return [f"{name:<10}: no trades"]
        w = (t.pnl_usd > 0).sum()
        return [f"{name:<10}: {len(t):3d} trades, {w} wins ({100 * w / len(t):.1f}%), "
                f"net ${t.pnl_usd.sum():+.2f}, avg ${t.pnl_usd.mean():+.2f}"]

    taken = tl[tl.traded] if not tl.empty else tl
    first, last = gold.index[0].date(), gold.index[-1].date()
    lines = [f"Data            : {SYMBOL} 5m, {first} -> {last} (New York time), SMT vs {SMT_SYMBOL}",
             f"Signals         : {len(signals)} ({skipped} skipped: stop wider than 3 x ATR14)"]
    lines += stats(taken, "TRADED A+/B")
    for g in ("A+", "B", "C"):
        lines += stats(tl[tl.grade == g] if not tl.empty else tl, f"  grade {g}")
    if not taken.empty:
        lines.append("Exit reasons    : " + ", ".join(f"{k}={v}" for k, v in taken.reason.value_counts().items()))
    header = ("PRAFUL - ICT Session Scalper on gold | 0.01 lot | TP +$3, cross ✗ in trade direction, "
              f"indicator SL | spread ${SPREAD} | grades traded: {'/'.join(TRADE_GRADES)}\n")
    os.makedirs(a.out, exist_ok=True)
    tl.to_csv(os.path.join(a.out, "trades.csv"), index=False)
    with open(os.path.join(a.out, "summary.txt"), "w") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")
    print(header)
    print("\n".join(lines))
    print(f"\nTrade list: {os.path.join(a.out, 'trades.csv')}")


if __name__ == "__main__":
    main()

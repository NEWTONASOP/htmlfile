"""Slow / trend MA of OD SOFTWARE: SMA 40 on close (TradingView ta.sma).

Decoded from the script's inputs ("Slow MA Length" 40, "Slow MA type" SMA, "Slow Source"
close). It is the script's "Trend MA line" plot: matches it exactly on NSE:NIFTY 3m.
"""
from __future__ import annotations

import pandas as pd

LENGTH = 40
SOURCE = "Close"


def sma(df: pd.DataFrame, n: int = LENGTH) -> pd.Series:
    return df[SOURCE].rolling(n, min_periods=n).mean().rename(f"sma{n}")

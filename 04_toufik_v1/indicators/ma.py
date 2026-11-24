"""MA 10 - slow moving average on close.

The client wrote "MA", so the default is a Simple Moving Average (TradingView ta.sma).
The type is configurable: "sma" (default) or "ema".
"""
from __future__ import annotations

import pandas as pd

from .ema import pine_ema

LENGTH = 10
SOURCE = "Close"
TYPE = "sma"


def ma(df: pd.DataFrame, n: int = LENGTH, ma_type: str = TYPE) -> pd.Series:
    src = df[SOURCE]
    if ma_type == "sma":
        out = src.rolling(n).mean()          # Pine ta.sma
    elif ma_type == "ema":
        out = pine_ema(src, n)
    else:
        raise ValueError(f"unknown MA type {ma_type!r} (use 'sma' or 'ema')")
    return out.rename(f"ma{n}")

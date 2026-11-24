"""Williams Fractal (TradingView built-in "Williams fractal", STD;Whilliams_Fractals v31).

Port of williams_fractal.pine (same folder), Periods n = 7.

For a pivot candle p (the candle the arrow is drawn on):
  * right side: the n candles after p have a strictly lower high (up arrow) /
    strictly higher low (down arrow);
  * left side: the n candles before p are strictly lower/higher, or the 1-4 candles
    right before p may be equal (<= / >=) and then n further candles strictly lower/higher
    (the script's "Frontier0..4" flags).
The script evaluates this n candles after p (`offset=-n` draws the arrow back on p). Comparisons
with candles before the start of the data are na in Pine, i.e. false.

Output columns, indexed by the pivot candle p (the arrow's position on the chart):
  up_arrow    green arrow above the candle (swing high)  -> PE in Suneet's strategy
  down_arrow  red arrow below the candle (swing low)     -> CE
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS = 7


def _fractal(v: np.ndarray, p: int, n: int, up: bool) -> bool:
    """True if candle p is a fractal (up: highs, down: lows), confirmed n candles later."""
    N = len(v)
    if p + n >= N:                                   # not confirmed yet (needs n candles after p)
        return False
    x = v[p]
    beyond = (lambda a: a < x) if up else (lambda a: a > x)       # strictly lower high / higher low
    equal_ok = (lambda a: a <= x) if up else (lambda a: a >= x)
    if not all(beyond(v[p + i]) for i in range(1, n + 1)):        # "DownFrontier": candles after p
        return False
    for k in range(5):                                            # "UpFrontier0..4": candles before p
        if p - k - n < 0:                                         # na -> false
            continue
        if all(equal_ok(v[p - j]) for j in range(1, k + 1)) and \
           all(beyond(v[p - k - i]) for i in range(1, n + 1)):
            return True
    return False


def williams_fractal(df: pd.DataFrame, n: int = PERIODS) -> pd.DataFrame:
    h, lo = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    up = np.array([_fractal(h, p, n, True) for p in range(len(df))])
    down = np.array([_fractal(lo, p, n, False) for p in range(len(df))])
    return pd.DataFrame({"up_arrow": up, "down_arrow": down}, index=df.index)

"""Option premium estimated from NIFTY spot (Black-Scholes, European options).

No historical option prices are used. The premium of each leg is calculated from:
  S      NIFTY spot at that moment
  K      the leg's strike
  T      time left to expiry (15:30 IST on expiry day), in years (calendar days / 365)
  sigma  implied volatility = India VIX / 100 at that moment
  r      risk-free rate (6.5%)
This is an approximation: real premiums also depend on each strike's own implied
volatility (smile/skew), bid-ask spreads and demand.
"""
from __future__ import annotations

import math

import numpy as np

RISK_FREE = 0.065
_erf = np.frompyfunc(math.erf, 1, 1)


def _ncdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + _erf(np.asarray(x, float) / math.sqrt(2.0)).astype(float))


def bs_price(S, K, T, sigma, is_call, r: float = RISK_FREE) -> np.ndarray:
    """Vectorised Black-Scholes price. At expiry (T <= 0) returns intrinsic value."""
    S, K, T, sigma = (np.asarray(v, float) for v in (S, K, T, sigma))
    is_call = np.asarray(is_call, bool)
    S, K, T, sigma, is_call = np.broadcast_arrays(S, K, T, sigma, is_call)
    intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
    live = (T > 1e-9) & (sigma > 0)
    out = intrinsic.copy()
    if live.any():
        s, k, t, v, c = S[live], K[live], T[live], sigma[live], is_call[live]
        sq = v * np.sqrt(t)
        d1 = (np.log(s / k) + (r + 0.5 * v * v) * t) / sq
        d2 = d1 - sq
        disc = np.exp(-r * t)
        call = s * _ncdf(d1) - k * disc * _ncdf(d2)
        put = k * disc * _ncdf(-d2) - s * _ncdf(-d1)
        out[live] = np.where(c, call, put)
    return out

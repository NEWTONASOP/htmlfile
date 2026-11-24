"""ICT Session Scalper Toolkit - Python port of the signal engine.

Original Pine source: ict_session_scalper.pine (same folder). Default inputs, New York time.
Ported in the script's own order, bar by bar:
  sessions/killzones -> liquidity pools (pivots 3, equal highs/lows, Asia H/L, PDH/PDL)
  -> sweep scan (the ✗ marks) -> midnight open, NDOG/NWOG -> displacement -> chart-TF
  FVG/IFVG engine -> 1H and daily FVGs -> premium/discount -> SMT -> signal engine with
  stop cap and A+/B/C grading.
Drawing-only parts (boxes, labels, dashboard, RTH gap, volume imbalances) are left out.
Differences from TradingView: Yahoo data instead of TradingView's feed; the 1H and daily FVG
history (used only for grading) is built from completed hours/days of the 5-minute data.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# ---- inputs (script defaults) ----
PIV_LEN = 3
EQ_TOL_MULT = 0.15
DISP_MULT = 1.5
ONLY_DISP_FVG = True
FVG_MAX = 50
POOL_MAX = 90
HTF_MAX = 8
EQ_LEN = 120
SMT_LEN = 20
WINDOW_BARS = 30
ONLY_KZ = True
SL_ATR = 3.0              # stop cap mode "Auto" on a non-NQ symbol -> 3 x ATR14
STRICT_SL = True
MIN_RR = 2.0
ASIA = (18 * 60, 2 * 60)
LONDON_KZ = (2 * 60, 5 * 60)
NY_KZ = (9 * 60, 10 * 60 + 30)


def _in_session(mins: int, s: tuple) -> bool:
    a, b = s
    return a <= mins < b if a < b else (mins >= a or mins < b)


def _rma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1] = np.nanmean(x[:n])
        for i in range(n, len(x)):
            out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def _atr(h, lo, c, n):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(pc), h - lo, np.maximum(h - lo, np.maximum(abs(h - pc), abs(lo - pc))))
    return _rma(tr, n)


def _pivots(h, lo, L):
    """ta.pivothigh/pivotlow(L, L) values on the confirmation bar."""
    n = len(h)
    ph, pl = np.full(n, np.nan), np.full(n, np.nan)
    for t in range(2 * L, n):
        p = t - L
        if h[p] > h[p - L:p].max() and h[p] >= h[p + 1:t + 1].max():
            ph[t] = h[p]
        if lo[p] < lo[p - L:p].min() and lo[p] <= lo[p + 1:t + 1].min():
            pl[t] = lo[p]
    return ph, pl


def run(df: pd.DataFrame, smt: pd.DataFrame | None, mintick: float) -> tuple[pd.DataFrame, list[dict]]:
    """df/smt: 5-minute OHLC in New York time. Returns (per-bar frame, signal list)."""
    idx = df.index
    O, H, L, C = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    n = len(df)
    sH = smt["High"].reindex(idx).to_numpy(float) if smt is not None else np.full(n, np.nan)
    sL = smt["Low"].reindex(idx).to_numpy(float) if smt is not None else np.full(n, np.nan)

    atr50, atr14 = _atr(H, L, C, 50), _atr(H, L, C, 14)
    pivH, pivL = _pivots(H, L, PIV_LEN)
    body = np.abs(C - O)
    body_avg = pd.Series(body).rolling(20).mean().to_numpy()
    disp_up = (C > O) & (body > DISP_MULT * body_avg)
    disp_dn = (C < O) & (body > DISP_MULT * body_avg)
    eq_mid = (pd.Series(H).rolling(EQ_LEN).max() + pd.Series(L).rolling(EQ_LEN).min()).to_numpy() / 2
    low_min_prev = pd.Series(L).rolling(SMT_LEN).min().shift(1).to_numpy()
    high_max_prev = pd.Series(H).rolling(SMT_LEN).max().shift(1).to_numpy()
    s_low_min_prev = pd.Series(sL).rolling(SMT_LEN).min().shift(1).to_numpy()
    s_high_max_prev = pd.Series(sH).rolling(SMT_LEN).max().shift(1).to_numpy()

    # futures trading day: starts 18:00 New York (TradingView daily bar for COMEX)
    tday = np.array([(t + pd.Timedelta(hours=6)).date() for t in idx])
    day_hi = pd.Series(H).groupby(tday).max()
    day_lo = pd.Series(L).groupby(tday).min()
    days = list(day_hi.index)
    prev_day = {d: days[k - 1] for k, d in enumerate(days) if k > 0}

    # state
    pools: list[dict] = []          # px, buy, swept, eq
    fvgs: list[dict] = []           # top, bot, dir, state, birth, tapped
    htf: list[dict] = []            # top, bot, dir
    h1 = [math.nan] * 3; l1 = [math.nan] * 3          # a, b, c (a = newest completed hour)
    hd = [math.nan] * 3; ld = [math.nan] * 3
    hour_hi = hour_lo = math.nan
    aH = aL = math.nan
    mop = ndog_mid = nwog_mid = math.nan
    last_smt_bull = last_smt_bear = None
    arm_long = arm_short = None
    arm_long_low = arm_short_high = math.nan
    arm_long_eq = arm_short_eq = 1
    disp_long = disp_short = None
    signals: list[dict] = []
    rows = []

    def add_pool(is_buy, px, eq0, tol):
        for p in pools:
            if not p["swept"] and p["buy"] == is_buy and abs(p["px"] - px) <= tol:
                p["px"] = max(p["px"], px) if is_buy else min(p["px"], px)
                p["eq"] += 1
                return
        pools.append(dict(px=px, buy=is_buy, swept=False, eq=eq0))
        if len(pools) > POOL_MAX:
            pools.pop(0)

    def add_htf(top, bot, d):
        htf.append(dict(top=top, bot=bot, dir=d))
        if len(htf) > HTF_MAX:
            htf.pop(0)

    prev_asia = False
    for i in range(n):
        t = idx[i]
        mins = t.hour * 60 + t.minute
        prev_t = idx[i - 1] if i > 0 else None
        in_asia = _in_session(mins, ASIA)
        in_lkz, in_nkz = _in_session(mins, LONDON_KZ), _in_session(mins, NY_KZ)
        new_globex = t.hour == 18 and (prev_t is None or prev_t.hour != 18)
        tol = atr50[i] * EQ_TOL_MULT

        # --- liquidity pools ---
        if not math.isnan(pivH[i]):
            add_pool(True, pivH[i], 1, tol)
        if not math.isnan(pivL[i]):
            add_pool(False, pivL[i], 1, tol)
        if in_asia and not prev_asia:
            aH, aL = H[i], L[i]
        elif in_asia:
            aH = max(H[i] if math.isnan(aH) else aH, H[i])
            aL = min(L[i] if math.isnan(aL) else aL, L[i])
        if prev_asia and not in_asia and not math.isnan(aH):
            add_pool(True, aH, 2, tol)
            add_pool(False, aL, 2, tol)
        if new_globex and tday[i] in prev_day:
            pd_ = prev_day[tday[i]]
            add_pool(True, float(day_hi[pd_]), 2, tol)
            add_pool(False, float(day_lo[pd_]), 2, tol)
        prev_asia = in_asia

        # --- sweep scan (✗ marks) ---
        swept_b, swept_s = [], []
        bsl_eq = ssl_eq = 1
        for p in pools:
            if not p["swept"]:
                if (H[i] > p["px"]) if p["buy"] else (L[i] < p["px"]):
                    p["swept"] = True
                    if p["buy"]:
                        swept_b.append(p["px"]); bsl_eq = max(bsl_eq, p["eq"])
                    else:
                        swept_s.append(p["px"]); ssl_eq = max(ssl_eq, p["eq"])
        swept_bsl, swept_ssl = bool(swept_b), bool(swept_s)

        # --- midnight open, NDOG / NWOG ---
        if t.hour == 0 and (prev_t is None or prev_t.hour != 0):
            mop = O[i]
        if new_globex and i > 0:
            g_top, g_bot = max(C[i - 1], O[i]), min(C[i - 1], O[i])
            if t.weekday() == 6:
                nwog_mid = (g_top + g_bot) / 2
            else:
                ndog_mid = (g_top + g_bot) / 2

        # --- chart-TF FVG / IFVG engine ---
        if i >= 2:
            if L[i] > H[i - 2] and (not ONLY_DISP_FVG or disp_up[i - 1]):
                fvgs.append(dict(top=L[i], bot=H[i - 2], dir=1, state=0, birth=i, tapped=False))
            if H[i] < L[i - 2] and (not ONLY_DISP_FVG or disp_dn[i - 1]):
                fvgs.append(dict(top=L[i - 2], bot=H[i], dir=-1, state=0, birth=i, tapped=False))
            while len(fvgs) > FVG_MAX:
                fvgs.pop(0)
        inv_bull = inv_bear = tap_bull = tap_bear = False
        for f in fvgs:
            st, top, bot, d = f["state"], f["top"], f["bot"], f["dir"]
            if st == 2:
                continue
            if st == 0:
                if d == -1 and C[i] > top:
                    f["state"] = 1; inv_bull = True
                elif d == 1 and C[i] < bot:
                    f["state"] = 1; inv_bear = True
                elif d == 1 and not f["tapped"] and i > f["birth"] and L[i] <= top and C[i] >= bot:
                    f["tapped"] = True; tap_bull = True
                elif d == -1 and not f["tapped"] and i > f["birth"] and H[i] >= bot and C[i] <= top:
                    f["tapped"] = True; tap_bear = True
            else:
                if d == -1:
                    if C[i] < bot:
                        f["state"] = 2
                    elif not f["tapped"] and L[i] <= top and C[i] >= bot:
                        f["tapped"] = True; tap_bull = True
                else:
                    if C[i] > top:
                        f["state"] = 2
                    elif not f["tapped"] and H[i] >= bot and C[i] <= top:
                        f["tapped"] = True; tap_bear = True

        # --- 1H and daily FVGs (grading context) ---
        new_hour = prev_t is not None and t.floor("h") != prev_t.floor("h")
        if new_hour and not math.isnan(hour_hi):
            h1 = [hour_hi, h1[0], h1[1]]; l1 = [hour_lo, l1[0], l1[1]]
            if not math.isnan(h1[2]):
                if l1[0] > h1[2]:
                    add_htf(l1[0], h1[2], 1)
                if h1[0] < l1[2]:
                    add_htf(l1[2], h1[0], -1)
        if new_hour or prev_t is None:
            hour_hi, hour_lo = H[i], L[i]
        else:
            hour_hi, hour_lo = max(hour_hi, H[i]), min(hour_lo, L[i])
        if prev_t is not None and tday[i] != tday[i - 1]:
            pd_ = tday[i - 1]
            hd = [float(day_hi[pd_]), hd[0], hd[1]]; ld = [float(day_lo[pd_]), ld[0], ld[1]]
            if not math.isnan(hd[2]):
                if ld[0] > hd[2]:
                    add_htf(ld[0], hd[2], 1)
                if hd[0] < ld[2]:
                    add_htf(ld[2], hd[0], -1)
        htf[:] = [z for z in htf if not ((z["dir"] == 1 and C[i] < z["bot"]) or (z["dir"] == -1 and C[i] > z["top"]))]

        # --- premium / discount, SMT ---
        in_premium = C[i] > eq_mid[i]
        smt_ok = not math.isnan(sH[i])
        nq_ll, nq_hh = L[i] < low_min_prev[i], H[i] > high_max_prev[i]
        es_ll, es_hh = sL[i] < s_low_min_prev[i], sH[i] > s_high_max_prev[i]
        if smt_ok and nq_ll and not es_ll:
            last_smt_bull = i
        if smt_ok and nq_hh and not es_hh:
            last_smt_bear = i

        # --- signal engine ---
        if swept_ssl:
            arm_long, arm_long_low, arm_long_eq, disp_long = i, L[i], ssl_eq, None
        if swept_bsl:
            arm_short, arm_short_high, arm_short_eq, disp_short = i, H[i], bsl_eq, None
        armed_long = arm_long is not None and i - arm_long <= WINDOW_BARS
        armed_short = arm_short is not None and i - arm_short <= WINDOW_BARS
        if armed_long:
            arm_long_low = min(arm_long_low, L[i])
            if disp_up[i]:
                disp_long = i
        if armed_short:
            arm_short_high = max(arm_short_high, H[i])
            if disp_dn[i]:
                disp_short = i
        kz_ok = (not ONLY_KZ) or in_lkz or in_nkz
        long_trig = armed_long and disp_long is not None and kz_ok and (inv_bull or tap_bull)
        short_trig = armed_short and disp_short is not None and kz_ok and (inv_bear or tap_bear)
        max_sl = SL_ATR * atr14[i]

        def in_htf(px):
            return any(z["bot"] <= px <= z["top"] for z in htf)

        def count(buy, ref, dist):
            return sum(1 for p in pools if not p["swept"] and p["buy"] == buy
                       and (0 < (p["px"] - ref) <= dist if buy else 0 < (ref - p["px"]) <= dist))

        def nearest(buy, ref):
            c = [p["px"] for p in pools if not p["swept"] and p["buy"] == buy and (p["px"] > ref if buy else p["px"] < ref)]
            return (min(c) if buy else max(c)) if c else math.nan

        def grade(is_long, entry, sl, sweep_eq):
            score = 0
            if in_htf(entry) or in_htf(sl):
                score += 1
            a = atr14[i]
            if any(not math.isnan(r) and abs(entry - r) < a for r in (mop, ndog_mid, nwog_mid)):
                score += 1
            last = last_smt_bull if is_long else last_smt_bear
            if last is not None and i - last <= WINDOW_BARS:
                score += 1
            if sweep_eq >= 2:
                score += 1
            if count(is_long, entry, a * 12) >= 2:
                score += 1
            if is_long != in_premium:
                score += 1
            if count(not is_long, entry, a * 3) >= 2:
                score -= 1
            return "A+" if score >= 4 else "B" if score >= 2 else "C"

        for is_long, trig in ((True, long_trig), (False, short_trig)):
            if not trig:
                continue
            entry = C[i]
            sl = arm_long_low - 2 * mintick if is_long else arm_short_high + 2 * mintick
            dist = entry - sl if is_long else sl - entry
            if STRICT_SL and dist > max_sl:
                signals.append(dict(i=i, time=t, side="BUY" if is_long else "SELL", skipped=True,
                                    entry=entry, sl=sl, grade=None))
                continue
            g = grade(is_long, entry, sl, arm_long_eq if is_long else arm_short_eq)
            tp1 = nearest(is_long, entry)
            tpf = (max(tp1 if not math.isnan(tp1) else entry + MIN_RR * dist, entry + MIN_RR * dist) if is_long
                   else min(tp1 if not math.isnan(tp1) else entry - MIN_RR * dist, entry - MIN_RR * dist))
            signals.append(dict(i=i, time=t, side="BUY" if is_long else "SELL", skipped=False, grade=g,
                                entry=entry, sl=sl, tp1=tp1, tp=tpf))
            if is_long:
                arm_long = None
            else:
                arm_short = None

        rows.append((swept_b, swept_s, in_lkz or in_nkz))

    bars = pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C,
                         "swept_buyside": [r[0] for r in rows], "swept_sellside": [r[1] for r in rows],
                         "killzone": [r[2] for r in rows]}, index=idx)
    return bars, signals

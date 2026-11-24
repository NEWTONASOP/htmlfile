"""Interactive HTML chart: candles, SMA/EMA, Supertrend, RSI, crossover candles, entries, SL,
target, trailing SL and exits (what the dashboard chart has to draw)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.rsi import BULL_ABOVE, BEAR_BELOW


def make_chart(df: pd.DataFrame, trades: list, title: str, path: str, ma_names=("MA 1", "MA 2")) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    lab = lambda t: pd.Timestamp(t).strftime("%d %b %H:%M")  # noqa: E731
    x = [lab(t) for t in df.index]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=x, open=df.Open, high=df.High, low=df.Low, close=df.Close, name="NIFTY",
                                 increasing_line_color="#26a69a", decreasing_line_color="#ef5350"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=df.ma1, name=ma_names[0],
                             line=dict(color="#2962ff", width=1.4)), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=df.ma2, name=ma_names[1], line=dict(color="#ff9800", width=1.4)), 1, 1)
    st_up = np.where(df.st_dir == -1, df.supertrend, np.nan)
    st_dn = np.where(df.st_dir == 1, df.supertrend, np.nan)
    fig.add_trace(go.Scatter(x=x, y=st_up, name="Supertrend up", line=dict(color="#00a152", width=1.2)), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=st_dn, name="Supertrend down", line=dict(color="#d50000", width=1.2)), 1, 1)

    for col, sym, color, name, ycol in (("bull_cross", "triangle-up", "#90caf9", "Bullish crossover", "Low"),
                                        ("bear_cross", "triangle-down", "#ffcc80", "Bearish crossover", "High")):
        m = df[col].to_numpy()
        fig.add_trace(go.Scatter(x=np.array(x)[m], y=df[ycol][m], mode="markers", name=name,
                                 marker=dict(symbol=sym, size=7, color=color)), 1, 1)

    fig.add_trace(go.Scatter(x=x, y=df.rsi, name="RSI", line=dict(color="#7e57c2", width=1.2)), 2, 1)
    for lvl, c in ((BULL_ABOVE, "#00a152"), (BEAR_BELOW, "#d50000")):
        fig.add_hline(y=lvl, line=dict(color=c, width=1, dash="dot"), row=2, col=1)

    ex, ey, et, sx, sy, tx, ty, kx, ky, xx, xy, xt = ([] for _ in range(12))
    for t in trades:
        a, b = lab(t.entry_time), lab(t.exit_time)
        ex.append(a); ey.append(t.entry)
        et.append(f"{t.side} {t.strike} exp {t.expiry}<br>entry {t.entry:.2f} SL {t.stop:.2f} target {t.target:.2f}")
        # SL / trailing SL as a step line from entry to exit
        steps = list(t.sl_path) + [(t.exit_time, t.sl_path[-1][1])]
        for (t0, s0), (t1, _) in zip(steps, steps[1:]):
            sx += [lab(t0), lab(t1), None]; sy += [s0, s0, None]
        tx += [a, lab(t.t1_time) if t.t1_time is not None else b, None]; ty += [t.target, t.target, None]
        if t.t1_time is not None:
            kx.append(lab(t.t1_time)); ky.append(t.t1_fill)
        xx.append(b); xy.append(t.exit); xt.append(f"{t.reason}<br>{t.pnl_pts:+.2f} pts")
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="markers", name="Entry (crossover candle close)", text=et,
                             hoverinfo="text+x", marker=dict(symbol="star", size=13, color="#000",
                                                             line=dict(width=1, color="#fff"))), 1, 1)
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines", name="SL / trailing SL",
                             line=dict(color="#d50000", width=2, dash="dash")), 1, 1)
    fig.add_trace(go.Scatter(x=tx, y=ty, mode="lines", name="Target 1:3",
                             line=dict(color="#00a152", width=2, dash="dash")), 1, 1)
    fig.add_trace(go.Scatter(x=kx, y=ky, mode="markers", name="50% booked at 1:3",
                             marker=dict(symbol="diamond", size=11, color="#00a152")), 1, 1)
    fig.add_trace(go.Scatter(x=xx, y=xy, mode="markers", name="Exit", text=xt, hoverinfo="text+x",
                             marker=dict(symbol="x", size=11, color="#424242")), 1, 1)

    fig.update_layout(title=dict(text=title, font=dict(size=14)), template="plotly_white", height=850,
                      hovermode="x unified", legend=dict(orientation="h", y=-0.08),
                      xaxis=dict(type="category", nticks=12, rangeslider=dict(visible=False)),
                      xaxis2=dict(type="category", nticks=12))
    fig.write_html(path, include_plotlyjs=True, full_html=True)

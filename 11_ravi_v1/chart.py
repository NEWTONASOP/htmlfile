"""Interactive HTML chart (what the dashboard has to mark): NIFTY 5m candles with the 9 EMA and
all 7 ranges per day, breakout/entry candles; option premium of each trade with entry, SL,
trailing SL, target (when ON) and exit."""
from __future__ import annotations

import pandas as pd

RANGE_TIMES = ["09:20", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]


def make_chart(nifty: pd.DataFrame, opts: dict, trades: list, tested: list, path: str) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    days = [d for d, _ in tested]
    nb = nifty[pd.Index(nifty.index.date).isin(days)]
    nb = nb[nb.index.strftime("%H:%M") <= "15:25"]
    lab = lambda t: pd.Timestamp(t).strftime("%d %b %H:%M")  # noqa: E731
    x = [lab(t) for t in nb.index]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4], vertical_spacing=0.04,
                        subplot_titles=("NIFTY 5m: ranges, 9 EMA, signals", "Option premium of each trade"))
    fig.add_trace(go.Candlestick(x=x, open=nb.Open, high=nb.High, low=nb.Low, close=nb.Close, name="NIFTY",
                                 increasing_line_color="#26a69a", decreasing_line_color="#ef5350"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=nb.ema9, name="NIFTY 9 EMA", line=dict(color="#ff9800", width=1.3)), 1, 1)

    # ranges: high/low lines from the range candle until the next range candle
    rx, ry = [], []
    for d in days:
        db = nb[nb.index.date == d]
        starts = [t for t in db.index if t.strftime("%H:%M") in RANGE_TIMES]
        for k, s in enumerate(starts):
            e = starts[k + 1] if k + 1 < len(starts) else db.index[-1]
            hi, lo = db.at[s, "High"], db.at[s, "Low"]
            for lvl in (hi, lo):
                rx += [lab(s), lab(e), None]
                ry += [lvl, lvl, None]
    fig.add_trace(go.Scatter(x=rx, y=ry, mode="lines", name="Range high/low",
                             line=dict(color="#7e57c2", width=1.2, dash="dot")), 1, 1)

    for side, sym, color in (("CE", "triangle-up", "#00a152"), ("PE", "triangle-down", "#d50000")):
        tt = [t for t in trades if t.side == side]
        fig.add_trace(go.Scatter(
            x=[lab(t.signal_time) for t in tt], y=[nifty.at[t.signal_time, "Close"] for t in tt], mode="markers",
            name=f"{side} breakout + confirmations", marker=dict(symbol=sym, size=12, color=color),
            text=[f"{t.side} {t.strike} ({t.range_time} range)" for t in tt], hoverinfo="text+x"), 1, 1)

    # option premium during each trade + SL/trailing SL + target + entry/exit
    for k, t in enumerate(trades):
        o = opts[t.symbol].loc[t.entry_time:t.exit_time]
        fig.add_trace(go.Scatter(x=[lab(i) for i in o.index], y=o.Close, mode="lines", showlegend=k == 0,
                                 legendgroup="prem", name="Premium (close)", line=dict(color="#455a64", width=1.4),
                                 text=t.symbol, hoverinfo="text+y"), 2, 1)
        steps = list(t.sl_path) + [(t.exit_time, t.sl_path[-1][1])]
        sx, sy = [], []
        for (a, s0), (b, _) in zip(steps, steps[1:]):
            sx += [lab(a), lab(b)]
            sy += [s0, s0]
        fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines", showlegend=k == 0, legendgroup="sl",
                                 name="SL / trailing SL", line=dict(color="#d50000", width=1.6, dash="dash")), 2, 1)
        if t.target is not None:
            fig.add_trace(go.Scatter(x=[lab(t.entry_time), lab(t.exit_time)], y=[t.target, t.target], mode="lines",
                                     showlegend=k == 0, legendgroup="tg", name="Target",
                                     line=dict(color="#00a152", width=1.6, dash="dash")), 2, 1)
    fig.add_trace(go.Scatter(x=[lab(t.entry_time) for t in trades], y=[t.entry for t in trades], mode="markers",
                             name="Entry (next open)", marker=dict(symbol="star", size=12, color="#000"),
                             text=[f"{t.side} {t.symbol} entry {t.entry:.2f}" for t in trades], hoverinfo="text+x"), 2, 1)
    fig.add_trace(go.Scatter(x=[lab(t.exit_time) for t in trades], y=[t.exit for t in trades], mode="markers",
                             name="Exit", marker=dict(symbol="x", size=11, color="#424242"),
                             text=[f"{t.reason} {t.pnl:+.2f}" for t in trades], hoverinfo="text+x"), 2, 1)
    fig.update_layout(title="RAVI v1 NIFTY ORB", template="plotly_white", height=900, hovermode="closest",
                      legend=dict(orientation="h", y=-0.08),
                      xaxis=dict(type="category", nticks=14, rangeslider=dict(visible=False),
                                 categoryorder="array", categoryarray=x),
                      xaxis2=dict(type="category", nticks=14, categoryorder="array", categoryarray=x))
    fig.write_html(path, include_plotlyjs=True, full_html=True)

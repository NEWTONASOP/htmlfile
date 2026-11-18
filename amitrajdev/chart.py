"""Interactive HTML chart: candles + SMA 120 + LuxAlgo pivots (regular and missed) +
Reversal Entry Zones signals + entries/exits, Smoothed Heiken Ashi panel, and a strip with
the BUY/SELL status of all 4 conditions on every candle."""
from __future__ import annotations

import pandas as pd


def make_chart(full: pd.DataFrame, view: pd.DataFrame, lux_events: pd.DataFrame, trades: pd.DataFrame,
               stats: list[str], title: str, path: str, cond_names: list[str]) -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    lab = lambda ts: pd.DatetimeIndex(ts).strftime("%d %b %H:%M")  # noqa: E731
    x = lab(view.index)
    start = view.index[0]
    pos_of = {t: k for k, t in enumerate(full.index)}
    first = pos_of[start]

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.62, 0.23, 0.15],
                        subplot_titles=("Price, SMA 120, LuxAlgo pivots, Reversal Entry Zones",
                                        "Smoothed Heiken Ashi v1", "Conditions (green = BUY, red = SELL)"))
    fig.add_trace(go.Candlestick(x=x, open=view.Open, high=view.High, low=view.Low, close=view.Close,
                                 name="5m candles", increasing_line_color="#26a69a",
                                 decreasing_line_color="#ef5350"), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=view.sma120, name="SMA 120", line=dict(color="#7e57c2", width=1.8)),
                  row=1, col=1)

    # LuxAlgo pivots whose pivot candle is inside the view; hover shows the confirmation time
    if not lux_events.empty:
        ev = lux_events[lux_events.pivot_idx >= first].copy()
        if not ev.empty:
            ev["x"] = lab(full.index[ev.pivot_idx])
            ev["conf"] = lab(full.index[ev.confirm_idx])
            for (kind, missed), sym, color, name in (
                    (("high", False), "triangle-down", "#ef5350", "Pivot High"),
                    (("low", False), "triangle-up", "#26a69a", "Pivot Low"),
                    (("high", True), "diamond-open", "#ef5350", "Missed Pivot High"),
                    (("low", True), "diamond-open", "#26a69a", "Missed Pivot Low")):
                e = ev[(ev.kind == kind) & (ev.missed == missed)]
                if e.empty:
                    continue
                off = 1.0004 if kind == "high" else 0.9996
                fig.add_trace(go.Scatter(
                    x=e.x, y=e.price * off, mode="markers", name=name,
                    marker=dict(symbol=sym, size=12, color=color, line=dict(width=2, color=color)),
                    text=[f"{name} {p:.2f}<br>confirmed {c}" for p, c in zip(e.price, e.conf)],
                    hoverinfo="text+x"), row=1, col=1)

    # Reversal Entry Zones confirmations, drawn at the pivot like the indicator
    rz = full[(full.rez_signal != 0) & (full.rez_pivot_idx >= first)]
    for s, color, name, off in ((1, "#00b978", "Bullish Reversal", 0.9992), (-1, "#eb4040", "Bearish Reversal", 1.0008)):
        r = rz[rz.rez_signal == s]
        if r.empty:
            continue
        fig.add_trace(go.Scatter(
            x=lab(full.index[r.rez_pivot_idx.astype(int)]), y=r.rez_price * off, mode="markers+text",
            name=name, text=["BULL REV" if s == 1 else "BEAR REV"] * len(r),
            textposition="bottom center" if s == 1 else "top center", textfont=dict(size=9, color=color),
            marker=dict(symbol="square", size=7, color=color),
            hovertext=[f"{name} {p:.2f}<br>confirmed {c}" for p, c in zip(r.rez_price, lab(r.index))],
            hoverinfo="text+x"), row=1, col=1)

    # entries and exits
    if not trades.empty:
        for side, sym, color in (("BUY", "triangle-up", "#00c853"), ("SELL", "triangle-down", "#d50000")):
            t = trades[trades.side == side]
            if t.empty:
                continue
            fig.add_trace(go.Scatter(
                x=lab(pd.to_datetime(t.entry_time)), y=t.entry, mode="markers", name=f"{side} entry",
                marker=dict(symbol=sym, size=15, color=color, line=dict(width=1, color="black")),
                text=[f"{side} entry {p:.2f}" for p in t.entry], hoverinfo="text+x"), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=lab(pd.to_datetime(trades.exit_time)), y=trades.exit, mode="markers", name="Exit",
            marker=dict(symbol="x", size=12, color="black", line=dict(width=2)),
            text=[f"{s} exit {p:.2f}<br>{r}<br>P&L {q:+.2f}" for s, p, r, q in
                  zip(trades.side, trades.exit, trades.reason, trades.pnl_pts)],
            hoverinfo="text+x"), row=1, col=1)

    # Smoothed Heiken Ashi
    fig.add_trace(go.Candlestick(x=x, open=view.ha_open, high=view.ha_high, low=view.ha_low, close=view.ha_close,
                                 name="Smoothed HA", increasing_line_color="#00e676",
                                 decreasing_line_color="#ff1744", showlegend=False), row=2, col=1)

    # condition strip
    z = view[[f"c_{c}" for c in cond_names]].T.to_numpy()
    fig.add_trace(go.Heatmap(x=x, y=cond_names, z=z, zmin=-1, zmax=1, showscale=False,
                             colorscale=[[0, "#ef5350"], [0.5, "#bdbdbd"], [1, "#26a69a"]],
                             hovertemplate="%{y}: %{z}<extra>+1 BUY / -1 SELL</extra>"), row=3, col=1)

    fig.update_xaxes(type="category", nticks=12, rangeslider=dict(visible=False))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14), y=0.995, yanchor="top"),
        template="plotly_white", height=1050, hovermode="x unified",
        legend=dict(orientation="h", y=-0.06), margin=dict(t=250, l=60, r=20, b=80),
        annotations=list(fig.layout.annotations) + [dict(
            text="<br>".join(stats), x=0, y=1.0, xref="paper", yref="paper", xanchor="left",
            yanchor="bottom", align="left", showarrow=False, font=dict(family="monospace", size=11),
            yshift=22)],
    )
    fig.write_html(path, include_plotlyjs=True, full_html=True)

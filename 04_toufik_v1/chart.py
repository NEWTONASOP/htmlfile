"""Interactive HTML chart: 3-minute candles, EMA 4, MA 10, entries, exits, stop losses, stats."""
from __future__ import annotations

import pandas as pd


def make_chart(df: pd.DataFrame, trades: pd.DataFrame, stats: list[str], title: str, path: str,
               ema_col: str, ma_col: str) -> None:
    import plotly.graph_objects as go

    x = df.index.strftime("%d %b %H:%M")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=x, open=df.Open, high=df.High, low=df.Low, close=df.Close,
                                 name="3m candles", increasing_line_color="#26a69a",
                                 decreasing_line_color="#ef5350"))
    fig.add_trace(go.Scatter(x=x, y=df[ema_col], name=ema_col.upper().replace("EMA", "EMA "),
                             line=dict(color="#2962ff", width=1.6)))
    fig.add_trace(go.Scatter(x=x, y=df[ma_col], name=ma_col.upper().replace("MA", "MA "),
                             line=dict(color="#ff9800", width=1.6)))

    if not trades.empty:
        fmt = lambda s: pd.to_datetime(s).dt.strftime("%d %b %H:%M")  # noqa: E731
        for side, sym, color in (("CE", "triangle-up", "#00c853"), ("PE", "triangle-down", "#d50000")):
            t = trades[trades.side == side]
            if t.empty:
                continue
            fig.add_trace(go.Scatter(
                x=fmt(t.entry_time), y=t.entry, mode="markers", name=f"{side} entry",
                marker=dict(symbol=sym, size=13, color=color, line=dict(width=1, color="black")),
                text=[f"{side} entry {p:.2f}<br>SL {s:.2f}" for p, s in zip(t.entry, t.stop)],
                hoverinfo="text+x"))
        styles = {"Opposite crossover": ("circle-open", "#2962ff", "Exit: opposite crossover"),
                  "StopLoss": ("x", "black", "Stop-loss exit"),
                  "Square-off 15:15": ("square-open", "#757575", "Exit: square-off 15:15")}
        for reason, (sym, color, label) in styles.items():
            t = trades[trades.reason == reason]
            if t.empty:
                continue
            fig.add_trace(go.Scatter(
                x=fmt(t.exit_time), y=t.exit, mode="markers", name=label,
                marker=dict(symbol=sym, size=12, color=color, line=dict(width=2, color=color)),
                text=[f"{s} exit {p:.2f}<br>P&L {q:+.2f} pts" for s, p, q in zip(t.side, t.exit, t.pnl_pts)],
                hoverinfo="text+x"))

    fig.update_layout(
        title=dict(text=title, font=dict(size=15), y=0.99, yanchor="top"),
        xaxis=dict(type="category", nticks=12, rangeslider=dict(visible=False)),
        yaxis=dict(title="Price"),
        template="plotly_white", height=780, hovermode="x unified",
        legend=dict(orientation="h", y=-0.12),
        margin=dict(t=210, l=60, r=20, b=80),
        annotations=[dict(text="<br>".join(stats), x=0, y=1.0, xref="paper", yref="paper",
                          xanchor="left", yanchor="bottom", align="left", showarrow=False,
                          font=dict(family="monospace", size=12))],
    )
    fig.write_html(path, include_plotlyjs=True, full_html=True)

# TOUFIK – EMA 4 / MA 10 Strategy

Intraday crossover-and-reverse backtest on **3-minute** candles. Default: `RELIANCE.NS`,
last 5 sessions (about one week), data from the unofficial `yfinance` API.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: crossover entries, reversals, stop loss, costs, report |
| `indicators/ema.py` | EMA 4 on close (Pine `ta.ema`) |
| `indicators/ma.py` | MA 10 on close: SMA by default (Pine `ta.sma`), or EMA with `--ma-type ema` |
| `chart.py` | Interactive HTML chart: candles, EMA 4, MA 10, CE/PE entries, exits, stop-loss exits, stats |
| `data.py` | Data loader for this strategy: 1-minute yfinance data built into 3-minute candles |
| `results/` | Output of the last run: `trades.csv`, `summary.txt`, `bars_with_indicators.csv`, `chart.html` |

No Pine source is needed: EMA and SMA are standard TradingView indicators.

## Run

Run from the repository root (needs `yfinance`, `pandas`, `plotly`):

```bash
pip install -r requirements.txt
python 04_toufik_v1/strategy.py                              # RELIANCE.NS 3m, last 5 sessions
python 04_toufik_v1/strategy.py --sl-pct 0.5                 # stop loss %
python 04_toufik_v1/strategy.py --ma-type ema                # MA 10 as EMA instead of SMA
python 04_toufik_v1/strategy.py --qty 500 --brokerage 20 --cost-pct 0.05
python 04_toufik_v1/strategy.py --day 2026-11-17             # print one day's trades
```

Open `04_toufik_v1/results/chart.html` in a browser to see the chart.

## 3-minute data

yfinance has no 3-minute interval, so 1-minute candles are downloaded and grouped into
3-minute candles starting at 09:15 (09:15, 09:18, …), the same grid TradingView uses for NSE.
yfinance keeps 1-minute data for about the last 30 days, so `--sessions` can go up to about 20.

## Rules as implemented

| Item | Implementation |
|---|---|
| Indicators | EMA 4 and MA 10 on close. MA 10 is an SMA by default (`--ma-type ema` to change) |
| CE (BUY) | EMA 4 crosses **above** MA 10 (`ta.crossover`) on a completed candle |
| PE (SELL) | EMA 4 crosses **below** MA 10 (`ta.crossunder`) on a completed candle |
| Entry | Open of the candle right after the crossover candle closes |
| Exit / reversal | Every opposite crossover exits the open position and enters the other side at the same open. Never CE and PE together |
| Repeated signals | One action per crossover; nothing new while the same condition stays true |
| Stop loss | `--sl-pct` (default **1%**) from entry: CE below, PE above, checked on each candle's low/high. After a stop-loss exit, no new trade until the next fresh crossover |
| Session (assumed) | Intraday: entries only on candles opening before 15:00; anything open is squared off at 15:15 (close of the 15:12 candle). No signals carried overnight |
| Costs | `--cost-pct` round trip, % of entry value (default **0.05%**), plus `--brokerage` Rs per order (default 0; 2 orders per trade) |
| Report | Total trades, winning and losing trades (after costs), win rate, gross and net P&L, profit factor, max drawdown |
| Instrument | The backtest uses the RELIANCE stock price: CE = long, PE = short. Option premiums are not available from yfinance |

# Rakesh Rattan – EMA Crossover Strategy

Intraday backtest on 5-minute candles using 7 EMAs. Default: `RELIANCE.NS`, last 1 week
(5 sessions), quantity 50, data from the unofficial `yfinance` API.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: crossover entries, 1-tick stop loss, 50% at 1:1, rest at 1:2, report |
| `indicators/ema_set.py` | The 7 EMAs (15/30/35/40/45/50/60 of close, Pine `ta.ema`) and the 60 EMA crossover state |
| `data.py` | Data loader for this strategy: yfinance download, CSV loading, IST session |
| `results/` | Output of the last run (created when you run it) |

No Pine source is needed: all lines are standard TradingView EMAs.

## Run

Run from the repository root:

```bash
pip install -r requirements.txt
python rakesh/strategy.py                          # RELIANCE.NS 5m, last 5 sessions, qty 50
python rakesh/strategy.py --sessions 40 --cost-pct 0.05
python rakesh/strategy.py --day 2026-11-13         # print one day's trades
python rakesh/strategy.py --tick 0.05              # different tick size
```

Outputs go to `rakesh/results/`: `trades.csv`, `summary.txt` and `bars_with_indicators.csv`
(every EMA and the crossover flags per candle, to compare with TradingView).

## EMAs

| EMA | Colour | Role |
|---|---|---|
| 15 | Blue | Short-term |
| 30 | Sky Blue | |
| 35 | Yellow | |
| 40 | Green | |
| 45 | Dark Blue | |
| 50 | Red | |
| 60 | Black | Main / longest |

## Rules as implemented

| Item | Implementation |
|---|---|
| Timeframe | 5-minute candles |
| BUY signal | The **60 EMA (black) crosses above all the other EMAs**: it becomes the highest line (it was not the highest on the previous candle) |
| SELL signal | The **60 EMA crosses below all the other EMAs**: it becomes the lowest line |
| Entry | **Open of the next candle** after the crossover candle closes |
| Trading time | Entry candle must open before 15:00 (entries 09:15–15:00). Open trades are squared off at **15:15** |
| Stop loss | BUY: **1 tick below the crossover candle's low**. SELL: 1 tick above its high. The crossover candle is the one before the entry candle. Tick = ₹0.10 (`--tick`) |
| 1:1 | Book **50%** (25 of 50 qty) and move SL to **cost** (entry price) |
| 1:2 | Exit the remaining **50%** |
| Same candle | Stop checked first, then 1:1, then 1:2 (conservative) |
| Opposite crossover | Ignored while a trade is open. One trade at a time |
| Invalid setup | Skipped if the entry open is already beyond the stop (no risk to measure) |
| P&L | `pnl_pts` = per share averaged over the full quantity (50% at 1:1 + 50% at the final exit; 100% at the SL if 1:1 was never reached). `pnl_rs` = `pnl_pts` × qty |

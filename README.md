# Neeraj – Kyle Algo + Liquidity Swings Strategy (backtest)

Intraday 5-minute backtest for NSE stocks (default `RELIANCE.NS`, last 1 week = 5 sessions),
data from the unofficial `yfinance` API.

```bash
pip install -r requirements.txt
python backtest.py                         # RELIANCE.NS, last 5 complete sessions
python backtest.py --qty 100 --cost-pct 0.05
python backtest.py --csv my_5m_data.csv    # columns: Datetime,Open,High,Low,Close (IST)
```

Outputs go to `results/`: `trades.csv` (trade log), `summary.txt` (stats),
`bars_with_indicators.csv` (ribbon, signals and zones per candle, for checking against TradingView).

yfinance gives at most 60 days of 5m history. All of it is downloaded and used as indicator
warm-up, so the EMAs and pivots are settled before the backtest week starts.

## Rules as implemented

| Item | Implementation |
|---|---|
| Timeframe | 5-minute candles, NSE session 09:15–15:30 IST |
| Kyle ribbon | 15 EMAs of **high**, lengths 9, 12, …, 51 (as in the indicator source) |
| CALL entry | A candle **closes above every ribbon EMA** and the previous candle did not (fresh cross) → buy at the **next candle's open** |
| PUT entry | A candle **closes below every ribbon EMA** and the previous candle did not → short at the next candle's open |
| Opposite signal in a trade | **Reverse** (default): exit at the next open and enter the opposite side at the same price. With `--no-reverse`, opposite signals are ignored while in a trade |
| CALL exit | Next **confirmed RED (swing-high) Liquidity Swings zone** → exit at the next candle's open |
| PUT exit | Next **confirmed GREEN (swing-low) zone** → exit at the next candle's open |
| Zone confirmation | `ta.pivothigh/pivotlow(14, 14)`: the zone appears 14 candles after the pivot candle, which is when Liquidity Swings draws it. Only zones confirmed while the trade is open count |
| Stop loss | 1% from entry, checked against each candle's high/low; fills at the stop (or at the open if price gaps through it) |
| Square-off | Any open position closes at **15:15** (close of the 15:10–15:15 candle) |
| No new trades | No entry on the candle ending 15:15: the last entry fills at the 15:05 open, so an entry signal candle must close by 15:05. Liquidity-zone exits still act up to the 15:10 open |
| Instrument | CALL = long stock, PUT = short stock. P&L is per share on the underlying, before costs unless `--cost-pct` is set |
| Kyle BUY/SELL labels | Not used |

### Notes on the indicator settings

* **Kyle Algo (Sensitivity 1.7, Keltner 11, ATR 10, Factor 1):** these inputs only drive the
  Supertrend BUY/SELL labels and the candle colours. The EMA ribbon has no inputs, so these
  settings **do not change any trade**. They are recorded in `backtest.py` for reference only.
* **Liquidity Swings (Lookback 14, Wick Extremity, Filter by Count, 0):** Swing Area only
  changes the zone's box bounds (logged for reference). A Count filter of 0 hides no zones,
  so every confirmed pivot is an exit event.
* Pivot ties: the pivot candle must be strictly higher (or lower) than the 14 candles to its
  left and at least equal to the 14 to its right.
* "Fully above or below the ribbon" uses a strict comparison of close against the highest or
  lowest of the 15 EMAs.

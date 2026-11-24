# Neeraj – Kyle Algo + Liquidity Swings Strategy

Intraday 5-minute backtest. Entries from the Kyle Algo EMA ribbon, exits from
Liquidity Swings [LuxAlgo] zones.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: entries, exits, stop loss, session rules, report |
| `indicators/kyle_algo.py` | Kyle Algo EMA ribbon (Python) |
| `indicators/kyle_algo.pine` | Original Kyle Algo v1 Pine source (MPL 2.0) |
| `indicators/liquidity_swings.py` | Liquidity Swings pivots and drawn zones (Python port) |
| `indicators/liquidity_swings.pine` | Original Liquidity Swings [LuxAlgo] Pine source (© LuxAlgo, CC BY-NC-SA 4.0) |
| `data.py` | Data loader for this strategy: yfinance download, CSV loading, IST session |
| `results/` | Output of the last run (created when you run it) |

## Run

Default: `RELIANCE.NS`, last 1 week (5 sessions), data from the unofficial `yfinance` API.
Run from the repository root:

```bash
pip install -r requirements.txt
python 01_neeraj_v1/strategy.py                          # RELIANCE.NS, last 5 complete sessions
python 01_neeraj_v1/strategy.py --qty 100 --cost-pct 0.05
python 01_neeraj_v1/strategy.py --exit-at confirm        # exits you could take live
python 01_neeraj_v1/strategy.py --zones 2026-11-13       # list the zones drawn on a day
python 01_neeraj_v1/strategy.py --csv my_5m_data.csv     # columns: Datetime,Open,High,Low,Close (IST)
```

Outputs go to `01_neeraj_v1/results/`: `trades.csv` (trade log), `summary.txt` (stats),
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
| Positions | `--mode multi` (default): **every fresh signal opens its own trade**, so several CALLs and PUTs can be open at the same time. Each trade closes on its own: its zone, its 1% SL or 15:15 |
| Other modes | `--mode reverse`: one position, and an opposite signal reverses it. `--mode hold` (or `--no-reverse`): one position, and opposite signals are ignored until it closes |
| CALL exit | Next **RED (swing-high) Liquidity Swings zone** |
| PUT exit | Next **GREEN (swing-low) zone** |
| Exit timing, `--exit-at swing` (default) | Matches manual chart reading: exit at the **close of the swing candle** where the zone box starts, for the first zone whose swing candle is at or after the entry. ⚠️ **Hindsight:** a zone is only known 14 candles after its swing candle, so these exits can't be taken live and the results are overstated |
| Exit timing, `--exit-at confirm` | Tradable live: exit at the next candle's open after the zone box **appears** on the chart (when a later candle first trades back into the zone) |
| Stop loss | 1% from entry, checked against each candle's high/low; fills at the stop (or at the open if price gaps through it) |
| Square-off | Any open position closes at **15:15** (close of the 15:10–15:15 candle) |
| No new trades | No entry on the candle ending 15:15: the last entry fills at the 15:05 open, so an entry signal candle must close by 15:05. Liquidity-zone exits still act up to the 15:10 open |
| Instrument | CALL = long stock, PUT = short stock. P&L is per share on the underlying, before costs unless `--cost-pct` is set |
| Kyle BUY/SELL labels | Not used |

### Notes on the indicator settings

* **Kyle Algo (Sensitivity 1.7, Keltner 11, ATR 10, Factor 1):** these inputs only drive the
  Supertrend BUY/SELL labels and the candle colours. The EMA ribbon has no inputs, so these
  settings **do not change any trade**. They are recorded in `indicators/kyle_algo.py` for reference only.
* **Liquidity Swings (Lookback 14, Wick Extremity, Filter by Count, 0):** ported from the
  LuxAlgo source (`get_counts` / `set_zone`). A zone box is only **drawn** once a later
  candle trades back into the zone (count crosses above 0). Swings that price never
  revisits before the next swing are never drawn and are ignored for exits. A drawn
  zone can therefore appear more than 14 candles after its swing candle.
* List the zones drawn on a day, to compare with TradingView:
  `python 01_neeraj_v1/strategy.py --zones 2026-11-13`
* Pivot ties: the pivot candle must be strictly higher (or lower) than the 14 candles to its
  left and at least equal to the 14 to its right.
* "Fully above or below the ribbon" uses a strict comparison of close against the highest or
  lowest of the 15 EMAs.

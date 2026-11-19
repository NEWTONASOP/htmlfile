# ASHISHKUMARVERMA – ORB (Opening Range Breakout) Strategy

Intraday ORB backtest on the stock's **spot** price, with RVOL and gap filters and a
9 EMA exit. Default: `RELIANCE.NS`, last 5 sessions, data from the unofficial `yfinance` API.
Strategy only (no chart or dashboard).

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: filters, alert candle, breakout entry, capped stop loss, 9 EMA exit, square-off, report |
| `indicators/orb.py` | Opening candle (09:15–09:30), gap, and the alert candle for each day |
| `indicators/rvol.py` | RVOL, length 20 (relative volume) |
| `indicators/ema.py` | 9 EMA of the 15-minute closes |
| `data.py` | Data loader: 1-minute yfinance OHLCV, grouped into 15-minute candles |
| `results/` | Output of the last run: `days.csv` (filters and setup per day), `trades.csv`, `summary.txt` |

## Run

Run from the repository root:

```bash
pip install -r requirements.txt
python ashishkumarverma/strategy.py                   # RELIANCE.NS, last 5 sessions
python ashishkumarverma/strategy.py --sessions 20     # about one month
python ashishkumarverma/strategy.py --rr 2            # optional fixed 1:2 target (default: none)
python ashishkumarverma/strategy.py --min-rvol 1.5 --max-gap-pct 2 --max-sl-pct 1 --last-entry 13:30
```

RVOL needs volume, so use a **stock**. Index symbols such as `^NSEI` have no volume on Yahoo.

## Data: 1-minute candles only, 15-minute built from them

Only **1-minute** OHLCV candles are downloaded. The 15-minute candles are **built in the
code** from them (Open = first open, High = highest high, Low = lowest low, Close = last
close, Volume = sum), on the 09:15, 09:30, … grid.

| Candles | Used for |
|---|---|
| 1-minute (downloaded) | Finding the breakout minute, the entry price (that minute's close), the stop loss and the 15:00 square-off |
| 15-minute (built) | Opening candle, alert candle, RVOL, 9 EMA and the 9 EMA exit |

yfinance keeps 1-minute data for about the last 30 days, so `--sessions` can go up to about
20. The oldest day in the data has no earlier candles for RVOL and is skipped.

## Rules as implemented

| # | Item | Implementation |
|---|---|---|
| 1 | Timeframe | 15-minute candles for levels, filters and the EMA exit |
| 2 | Opening candle | 09:15–09:30: **Opening High** and **Opening Low** |
| 3 | RVOL filter | RVOL(20) **≥ 1.5 on both the opening candle and the alert candle**, otherwise no trade. RVOL = candle volume ÷ average volume of the last 20 fifteen-minute candles (including this one), continuing across days. FYERS does not publish its formula; this is the standard definition |
| 4 | Gap filter | 09:15 open vs the previous day's close: **more than 2%** up or down = no trade (exactly 2% still trades) |
| 5 | F&O ban | Not applied (dashboard item) |
| 6 | Alert candle | The **first** 15-minute candle after 09:30, at any time of day, that **closes above Opening High** (CE) or **below Opening Low** (PE). The first such close decides the direction. Its high / low are the breakout levels |
| 7 | Entry | Any time after the alert candle closes (not necessarily the next candle): the first 1-minute candle that trades **above Alert High** (CE) or **below Alert Low** (PE). Filled at that minute's **close**. **No entry from 13:30** |
| 8 | Stop loss | CE: Alert Low. PE: Alert High. If more than **1%** from the entry, moved to exactly 1% |
| 9 | Target | **None** by default; `--rr` adds an optional fixed target |
| 10 | Exit | CE: a 15-minute candle **closes below the 9 EMA**; PE: one **closes above** it. Exit at the **next 15-minute candle open**. Only candles that close after the entry count |
| 11 | Position | One trade per stock per day, no re-entry. P&L is in points per share (× your lot size for one lot) |
| 12 | Square-off | **15:00** (close of the 14:59 one-minute candle) |
| – | Same minute | If a minute touches the stop loss, the stop counts (checked before any target) |

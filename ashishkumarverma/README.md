# ASHISHKUMARVERMA – ORB (Opening Range Breakout) Strategy

Intraday ORB backtest on the stock's **spot** price, with RVOL and gap filters and a
9 EMA exit. Default: `RELIANCE.NS`, last 5 sessions, data from the unofficial `yfinance` API.
Strategy only (no chart or dashboard).

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: filters, alert candle, breakout entry, capped stop loss, 9 EMA exit, square-off, report |
| `indicators/orb.py` | Opening candle (09:15–09:30), gap, and the alert candle for each day |
| `indicators/rvol.py` | RVOL, length 20: candle volume vs the same 15-minute slot over the previous 20 days |
| `indicators/ema.py` | 9 EMA of the 15-minute closes |
| `data.py` | Data loader: 1-minute yfinance OHLCV (grouped into 15-minute candles) and Yahoo's 15-minute bars for the RVOL history |
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

## Data

| Candles | Source | Used for |
|---|---|---|
| 1-minute | Downloaded from yfinance (about the last 30 days) | Breakout minute, entry price (that minute's close), stop loss, 15:00 square-off |
| 15-minute | **Built** from the 1-minute candles (Open = first open, High = highest high, Low = lowest low, Close = last close), on the 09:15, 09:30, … grid | Opening candle, alert candle, 9 EMA and the 9 EMA exit |
| 15-minute | Downloaded from yfinance (about the last 60 days) | RVOL (candle volume and its 20-day slot history) and the previous day's close for the gap |

Because RVOL needs 20 earlier days of the same time slot, it uses Yahoo's 15-minute bars,
which go back about 60 days; both the candle volume and its average come from that one
source. Their prices match the candles built from 1-minute data. Yahoo's 09:15 volume is
lower than the sum of its 1-minute candles (the 1-minute data likely includes the pre-open
auction), which is why one source is used for both parts of the ratio.

`--sessions` can go up to about 20 (the 1-minute data limit).

## Rules as implemented

| # | Item | Implementation |
|---|---|---|
| 1 | Timeframe | 15-minute candles for levels, filters and the EMA exit |
| 2 | Opening candle | 09:15–09:30: **Opening High** and **Opening Low** |
| 3 | RVOL filter | RVOL(20) **≥ 1.5 on both the opening candle and the alert candle**, otherwise no trade. RVOL = candle volume ÷ **average volume of the same 15-minute time slot over the previous 20 trading days** (e.g. today's 09:15 candle vs the last 20 days' 09:15 candles; today not included), as confirmed for FYERS. `--rvol-mode candles` uses the last 20 candles instead |
| 4 | Gap filter | 09:15 open vs the previous day's close (from the 15-minute data): **more than 2%** up or down = no trade (exactly 2% still trades) |
| 5 | F&O ban | Not applied (dashboard item) |
| 6 | Alert candle | The **first** 15-minute candle after 09:30, at any time of day, that **closes above Opening High** (CE) or **below Opening Low** (PE). The first such close decides the direction. Its high / low are the breakout levels |
| 7 | Entry | Any time after the alert candle closes (not necessarily the next candle): the first 1-minute candle that trades **above Alert High** (CE) or **below Alert Low** (PE). Filled at that minute's **close**. **No entry from 13:30** |
| 8 | Stop loss | CE: Alert Low. PE: Alert High. If more than **1%** from the entry, moved to exactly 1% |
| 9 | Target | **None** by default; `--rr` adds an optional fixed target |
| 10 | Exit | CE: a 15-minute candle **closes below the 9 EMA**; PE: one **closes above** it. Exit at the **next 15-minute candle open**. Only candles that close after the entry count |
| 11 | Position | One trade per stock per day, no re-entry. P&L is in points per share (× your lot size for one lot) |
| 12 | Square-off | **15:00** (close of the 14:59 one-minute candle) |
| – | Same minute | If a minute touches the stop loss, the stop counts (checked before any target) |

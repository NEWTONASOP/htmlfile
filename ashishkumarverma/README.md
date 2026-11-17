# ASHISHKUMARVERMA – ORB (Opening Range Breakout) Strategy

Intraday ORB backtest on the underlying **spot** price. Levels from **15-minute** candles,
breakout, stop loss and target checked on **1-minute** spot candles (the closest to "live
price" available from historical data). Default: `RELIANCE.NS`, last 5 sessions, data from
the unofficial `yfinance` API.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: setup, breakout entry, capped stop loss, R:R target, square-off, report |
| `indicators/orb.py` | ORB candle (09:15–09:30) and alert candle (09:30–09:45) levels and the day's setup |
| `data.py` | Data loader for this strategy: 1-minute yfinance spot data, grouped into 15-minute candles |
| `results/` | Output of the last run: `days.csv` (levels and setup per day), `trades.csv`, `summary.txt` |

No Pine source is needed: the strategy uses only candle highs, lows and closes.

## Run

Run from the repository root:

```bash
pip install -r requirements.txt
python ashishkumarverma/strategy.py                       # RELIANCE.NS, last 5 sessions
python ashishkumarverma/strategy.py --sessions 20         # about one month (1m data limit)
python ashishkumarverma/strategy.py --rr 2                # target 1:2
python ashishkumarverma/strategy.py --max-sl-pct 0.75     # SL cap
python ashishkumarverma/strategy.py --symbol ^NSEI        # NIFTY 50 spot
python ashishkumarverma/strategy.py --last-entry 14:30    # last time a new entry may trigger
```

yfinance keeps 1-minute data for about the last 30 days, so `--sessions` can go up to about 20.

## Rules as implemented

| # | Item | Implementation |
|---|---|---|
| 1 | Timeframe | 15-minute candles from 09:15 for the ORB and alert candles |
| 2–3 | ORB candle | 09:15–09:30: **ORB High** = its high, **ORB Low** = its low |
| 4–5 | Alert candle | 09:30–09:45. Close **above ORB High** = CE setup, **below ORB Low** = PE setup, **between** = no trade that day |
| 6 | Alert levels | **Alert High** and **Alert Low** = the alert candle's high and low |
| 7 | CE entry | After 09:45, the first time spot trades **above Alert High**. Fill at Alert High (or the 1-minute open if it opens above it) |
| 8 | PE entry | After 09:45, the first time spot trades **below Alert Low**. Fill at Alert Low (or the open if it opens below it) |
| 9 | No candle close | Breakouts are detected on 1-minute candles, so entries don't wait for a 15-minute close |
| 10 | Stop loss | CE: Alert Low. PE: Alert High. If that is more than **1%** (`--max-sl-pct`) from the entry, the SL is moved to exactly 1% |
| 11 | Target | `--rr` × risk from entry (default **1:1**) |
| 12 | Prices | Entry, SL and target all on the underlying spot price |
| 13 | One trade | Only the setup's direction is traded, at most one trade per day, no re-entry after an exit |
| 14 | Square-off | Anything open is closed at **15:15** (close of the 15:14 one-minute candle) |
| – | Last entry (assumed) | The spec gives no end time for entries; default: no new entry from **15:00** (`--last-entry`) |
| – | Same minute | If one 1-minute candle touches both SL and target, the SL counts first (conservative) |
| – | Costs | `--cost-pct` round trip, % of entry value (default 0.05%) |

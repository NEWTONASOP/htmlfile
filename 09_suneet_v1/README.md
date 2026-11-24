# SUNEET – Williams Fractal 7 (NIFTY, 1-minute)

Intraday backtest on NIFTY 50 1-minute candles with TradingView's built-in **Williams fractal**
(Periods 7): CE on the red arrow, PE on the green arrow, entered when the arrow appears live,
stop at the arrow candle's wick, exit and reverse on the opposite arrow. Data: unofficial `yfinance` API.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: arrow entries, wick stop loss, reversals, square-off, option strike/expiry per trade, report |
| `indicators/williams_fractal.pine` | Original source of TradingView's built-in "Williams fractal" (STD;Whilliams_Fractals v31) |
| `indicators/williams_fractal.py` | Python port of it |
| `data.py` | Data loader: 1-minute yfinance candles, or a CSV |
| `results/` | Output of the last run: `trades.csv`, `summary.txt`, `bars_with_indicators.csv` (gitignored) |

## Run

From the repository root:

```bash
pip install -r requirements.txt
python 09_suneet_v1/strategy.py                       # ^NSEI 1m, last 20 sessions (yfinance max ~20)
python 09_suneet_v1/strategy.py --sessions 5
python 09_suneet_v1/strategy.py --day 2026-11-18      # print one day's trades
python 09_suneet_v1/strategy.py --qty 65 --cost-pct 0.05
python 09_suneet_v1/strategy.py --csv nifty_1m.csv    # Datetime,Open,High,Low,Close (IST)
```

## Rules as implemented

| Item | Implementation |
|---|---|
| Instrument / timeframe | NIFTY 50 index (`^NSEI`), **1-minute** candles 09:15–15:14 IST |
| Indicator | Williams fractal, Periods **7**: a candle whose high (low) is strictly above (below) the 7 candles after it and the 7 candles before it; up to 4 candles right before it may be equal (TradingView's rule) |
| CE (BUY) | **Red arrow** below a candle (down fractal, swing low) |
| PE (SELL) | **Green arrow** above a candle (up fractal, swing high) |
| Signal | **When the arrow appears live**: the arrow on candle X is confirmed when candle **X+7** closes (**7 minutes** later on 1m); TradingView then draws it back on X |
| Entry | Open of the candle after the confirming candle (X+8) |
| Stop loss | The arrow candle's (X) **low wick** (CE) / **high wick** (PE). Checked from the entry candle on: hit when a candle's low ≤ SL (CE) or high ≥ SL (PE); fills at the SL, or at the open if price gapped through |
| Exit / reversal | When the next **opposite arrow** appears, exit and open the other side at the next candle's open. One position at a time |
| Same-side arrow in a trade | Ignored (stop unchanged) |
| After a stop loss | The next arrow of either side opens a new trade |
| Both arrows on one candle | No signal |
| Session | Entries only on candles opening **before 15:00**; anything open is squared off at **15:15** (close of the 15:14 candle). An arrow drawn on the previous day's last candles appears the next morning and is traded then (that is when it shows live); a signal on the day's last candle is not carried to the next day |
| Execution | Signal on the confirming candle's close, fill at the next open; if a candle hits the stop, the stop is taken before any new arrow on that candle |
| Options | P&L is in **NIFTY index points** (Yahoo has no option prices). Each trade lists its option: ATM = entry price rounded to 50; **CE strike = ATM − 50** (50 points ITM), **PE strike = ATM + 100** (100 points ITM); nearest weekly expiry (Tuesday, or the trading day before if Tuesday is a holiday in the data); on expiry day itself, next week's expiry |
| Quantity / costs | `--qty` (default **65**, 1 NIFTY lot) × index points; `--cost-pct` round trip (default 0) |

## Data

- yfinance 1-minute candles, used as they are. 1-minute data goes back only about 30 days
  (≈ 18–20 sessions).
- TradingView's NSE:NIFTY 1-minute data has no candles after 15:15 (last candle 15:14, 360 a day); Yahoo
  continues to 15:29. Those extra candles would change which candle is a fractal, so they are
  dropped.
- The first session is warm-up (a fractal needs 7 candles before it).
- Yahoo prices differ slightly from TradingView: over 27 Oct – 20 Nov 2026, 87 of 88 red and 89 of
  91 green TradingView arrows fall on the same candle with Yahoo data.

## Verified

- **Indicator:** the Python port matches TradingView's own output of the built-in (Periods 7):
  NSE:NIFTY **1m**, 2 – 20 Nov 2026: **218 / 218 red and 206 / 206 green arrows**; NSE:NIFTY 3m,
  21 Sep – 20 Nov 2026: 223 / 223 and 221 / 221; 0 differences. It also equals a line-by-line copy
  of the Pine loops on synthetic data with many equal highs/lows (the "equal candle" rule used
  64–70 times per dataset).
- **Data:** TradingView's 1-minute NIFTY day is 09:15–15:14 (360 candles). With Yahoo 1m data,
  205 of 209 red and 193 of 196 green TradingView arrows (2 – 20 Nov 2026) fall on the same candle.
- **Trades:** the engine was compared with a separately written simulator (per-trade forward
  scan, confirmation times computed by its own loop) on 3 synthetic 1-minute datasets: identical
  trades. Invariants: signal = arrow candle + 7, entry = next candle, stop = arrow candle's wick,
  no overlap, no entry from 15:00, everything out by 15:14, stop-loss fills at the stop or a gap open.
- **Hand-checked:** PE 18 Nov 2026: green arrow on 17 Nov 15:11 (high 25425.15 above the 7 highs
  before and after) appears at 18 Nov 09:18 (the 7th candle after it, across the night); entry
  09:19 open 25335.45, SL 25425.15, strike 25450 (ATM 25350 + 100), expiry 24 Nov; the red arrow
  on 09:15 appears at 09:22 → exit and reverse at the 09:23 open 25370.75 (−35.3).

# SUNEET – Williams Fractal 7 (NIFTY, 3-minute)

Intraday backtest on NIFTY 50 3-minute candles with TradingView's built-in **Williams fractal**
(Periods 7): CE on the red arrow, PE on the green arrow, entered when the arrow appears live,
stop at the arrow candle's wick, exit and reverse on the opposite arrow. Data: unofficial `yfinance` API.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: arrow entries, wick stop loss, reversals, square-off, option strike/expiry per trade, report |
| `indicators/williams_fractal.pine` | Original source of TradingView's built-in "Williams fractal" (STD;Whilliams_Fractals v31) |
| `indicators/williams_fractal.py` | Python port of it |
| `data.py` | Data loader: 1-minute yfinance data built into 3-minute candles, or a CSV |
| `results/` | Output of the last run: `trades.csv`, `summary.txt`, `bars_with_indicators.csv` (gitignored) |

## Run

From the repository root:

```bash
pip install -r requirements.txt
python suneet/strategy.py                       # ^NSEI 3m, last 20 sessions (yfinance max ~20)
python suneet/strategy.py --sessions 5
python suneet/strategy.py --day 2026-11-18      # print one day's trades
python suneet/strategy.py --qty 65 --cost-pct 0.05
python suneet/strategy.py --csv nifty_3m.csv    # Datetime,Open,High,Low,Close (IST)
```

## Rules as implemented

| Item | Implementation |
|---|---|
| Instrument / timeframe | NIFTY 50 index (`^NSEI`), 3-minute candles 09:15–15:12 IST |
| Indicator | Williams fractal, Periods **7**: a candle whose high (low) is strictly above (below) the 7 candles after it and the 7 candles before it; up to 4 candles right before it may be equal (TradingView's rule) |
| CE (BUY) | **Red arrow** below a candle (down fractal, swing low) |
| PE (SELL) | **Green arrow** above a candle (up fractal, swing high) |
| Signal | **When the arrow appears live**: the arrow on candle X is confirmed when candle **X+7** closes (21 minutes later on 3m); TradingView then draws it back on X |
| Entry | Open of the candle after the confirming candle (X+8) |
| Stop loss | The arrow candle's (X) **low wick** (CE) / **high wick** (PE). Checked from the entry candle on: hit when a candle's low ≤ SL (CE) or high ≥ SL (PE); fills at the SL, or at the open if price gapped through |
| Exit / reversal | When the next **opposite arrow** appears, exit and open the other side at the next candle's open. One position at a time |
| Same-side arrow in a trade | Ignored (stop unchanged) |
| After a stop loss | The next arrow of either side opens a new trade |
| Both arrows on one candle | No signal |
| Session | Entries only on candles opening **before 15:00**; anything open is squared off at **15:15** (close of the 15:12 candle). Arrows are not carried to the next day |
| Execution | Signal on the confirming candle's close, fill at the next open; if a candle hits the stop, the stop is taken before any new arrow on that candle |
| Options | P&L is in **NIFTY index points** (Yahoo has no option prices). Each trade lists its option: ATM = entry price rounded to 50; **CE strike = ATM − 50** (50 points ITM), **PE strike = ATM + 100** (100 points ITM); nearest weekly expiry (Tuesday, or the trading day before if Tuesday is a holiday in the data); on expiry day itself, next week's expiry |
| Quantity / costs | `--qty` (default **65**, 1 NIFTY lot) × index points; `--cost-pct` round trip (default 0) |

## Data

- yfinance has no 3-minute interval: 1-minute candles are grouped into 3-minute candles from
  09:15 (09:15, 09:18, …). 1-minute data goes back only about 30 days (≈ 18–20 sessions).
- TradingView's NSE:NIFTY 3-minute data has no candles after 15:15 (last candle 15:12); Yahoo
  continues to 15:29. Those extra candles would change which candle is a fractal, so they are
  dropped.
- The first session is warm-up (a fractal needs 7 candles before it).
- Yahoo prices differ slightly from TradingView: over 27 Oct – 20 Nov 2026, 87 of 88 red and 89 of
  91 green TradingView arrows fall on the same candle with Yahoo data.

## Verified

- **Indicator:** the Python port matches TradingView's own output of the built-in (Periods 7) on
  NSE:NIFTY 3m, 21 Sep – 20 Nov 2026 (5,059 candles): **223 / 223 red and 221 / 221 green arrows,
  0 differences**. It also equals a line-by-line copy of the Pine loops on synthetic data with
  many equal highs/lows (the "equal candle" rule used 28–32 times per dataset).
- **Trades:** the engine was compared with a separately written simulator (per-trade forward
  scan, confirmation times computed by its own loop) on 3 synthetic datasets: identical trades.
  Invariants: signal = arrow candle + 7, entry = next candle, stop = arrow candle's wick, no
  overlap, no entry from 15:00, everything out by 15:12, stop-loss fills at the stop or a gap open.
- **Hand-checked:** CE 18 Nov 2026: red arrow on 09:45 (low 25206.30 below the 7 lows before and
  after) appears at the 10:06 close; entry 10:09 open 25288.25, SL 25206.30, strike 25250 (ATM
  25300 − 50); the 10:03 green arrow appears at 10:24 → exit and reverse at the 10:27 open 25255.55
  (−32.70).

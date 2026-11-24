# RAJ v1 – MA crossover + Supertrend + RSI (NIFTY 50 ATM options)

Intraday backtest on NIFTY 50 (`^NSEI`) **2-minute and 5-minute** candles, data from the
unofficial `yfinance` API. The signal is decided on the index chart; each trade stands for the
ATM NIFTY option (CE or PE). Yahoo has no option prices, so P&L is in **NIFTY index points**.

## Folder

| File | What it is |
|---|---|
| `strategy.py` | Backtest: crossover + Supertrend + RSI entries, range filter, SL, 50% at 1:3, trailing SL, daily limits, report |
| `indicators/moving_averages.py` | SMA (`ta.sma`) and EMA (`ta.ema`, SMA-seeded) on close; type and period per line |
| `indicators/supertrend.py` | Supertrend (TradingView built-in / `ta.supertrend`, hl2, ATR = RMA) |
| `indicators/rsi.py` | RSI (`ta.rsi`, Wilder RMA), bullish > 60, bearish < 45 |
| `chart.py` | Interactive HTML chart: candles, SMA, EMA, Supertrend, RSI, crossover candles, entry, SL, target, trailing SL, exits |
| `data.py` | Data loader: yfinance 2m/5m or CSV, IST, 09:15–15:15 candles |
| `verify.py` | Independent check: indicators recomputed separately, setups rebuilt, every trade checked against the rules |
| `results/<2m|5m>/` | `trades.csv`, `signals.csv` (every candle with all 3 conditions and what happened), `summary.txt`, `bars_with_indicators.csv`, `chart.html` |

The official TradingView Pine sources of the four built-ins are saved next to the ports
(`indicators/sma.pine`, `ema.pine`, `supertrend.pine`, `rsi.pine`, fetched from TradingView's
`STD;SMA`, `STD;EMA`, `STD;Supertrend`, `STD;RSI`). The Python ports follow them; the SMA/EMA
"Smoothing" option is off (default) and not used.

## Run

From the repository root:

```bash
pip install -r requirements.txt
python 10_raj_v1/strategy.py                              # 2m and 5m, all Yahoo data
python 10_raj_v1/strategy.py --timeframe 5                # one timeframe
python 10_raj_v1/strategy.py --ma1 ema:9 --ma2 sma:21     # any MA type/period combination
python 10_raj_v1/strategy.py --st-atr 10 --st-factor 3 --rsi-len 21 --lot-size 65 --lots 2
python 10_raj_v1/strategy.py --zero-dte                   # trade the expiring contract on expiry day
python 10_raj_v1/strategy.py --day 2026-11-18             # print one day's trades
python 10_raj_v1/strategy.py --symbol RELIANCE.NS --sessions 5   # test the backtest on another Yahoo symbol
python 10_raj_v1/verify.py                                # independent check of the last run
```

Yahoo keeps 2m and 5m data for about 60 calendar days (2m: about 30 sessions, 5m: about 58).
The first session in the data is used only to warm up the indicators.

## Rules as implemented

| Item | Implementation |
|---|---|
| Timeframe | 2m or 5m (both run by default) |
| Moving averages | MA 1 and MA 2, each SMA or EMA with its own period, on close. Default **SMA 9** and **EMA 15** |
| Crossover | The **shorter-period** MA (fast) crosses the longer one (slow) on a completed candle: bullish = fast closes above slow after being at/below it (`ta.crossover`); bearish = the reverse. Equal periods: MA 1 is the fast line |
| Supertrend | ATR 10, factor 3 (TradingView default). Bullish = uptrend (green line), bearish = downtrend (red line), on the crossover candle |
| RSI | Length 21. Bullish **> 60**, bearish **< 45**, on the crossover candle |
| CE entry | Bullish crossover + bullish Supertrend + RSI > 60, **all on the same candle** |
| PE entry | Bearish crossover + bearish Supertrend + RSI < 45, all on the same candle |
| Entry price | **Close of the crossover candle itself** (no next-candle entry) |
| Candle filter | Skip if the crossover candle's High − Low is **more than 15 points** (exactly 15 is allowed) |
| Stop loss | CE: crossover candle **Low − 0.25**; PE: **High + 0.25** (5 ticks × 0.05) |
| Target | **1:3**: entry ± 3 × (entry − SL). **50%** of the quantity is booked there |
| After 1:3 | SL of the remaining 50% moves to **cost** (entry) |
| Trailing SL | Every **20 points** beyond the 1:3 price moves the SL **10 points**: target + 20 → cost + 10, target + 40 → cost + 20, … (best high for CE / low for PE since 1:3) |
| Checks | Everything on candles (no ticks): SL, 1:3 and trailing use candle **high/low** from the candle after entry. If one candle touches both SL and 1:3, the **SL counts first**. The candle that hits 1:3 also updates the trail; the new SL is checked from the next candle |
| Fills | SL / target at the level, or at the candle open if the candle opens beyond it |
| Remaining 50% | Exits only on the cost / trailing SL or at square-off (no second target) |
| Position | **One trade at a time**; any signal while a trade is open is ignored. After an exit, a signal on the same candle's close can enter |
| Trading time | No entries before 09:30: the crossover candle must **close at 09:30 or later** (5m: 09:25 candle on; 2m: 09:28 candle on). No last entry time |
| Square-off | **15:15** (close of the 15:10 5m / 15:13 2m candle). No overnight trades |
| Daily limits | Max **4 trades a day**. No more entries that day after **3 profitable or 3 losing trades in a row** (profit = total P&L of both halves > 0). Both reset each day |
| Options | **ATM** strike = entry index price rounded to 50. **Nearest Tuesday expiry** (trading day before if Tuesday is a holiday). 0-DTE toggle **OFF** (default): on expiry day the next week's expiry is used; ON: the expiring contract |
| P&L | `pnl_pts` = NIFTY points per unit averaged over the full quantity (50% at 1:3 + 50% at the final exit, or 100% at the SL). `pnl_rs` = `pnl_pts` × lot size × lots |
| Data | Candles from 15:15 on are dropped (TradingView NSE:NIFTY has none); indicators run continuously across days like the chart |

## Dashboard requirements (from the client's spec)

The backtest implements every setting below; the dashboard has to expose them:

| Setting | Default | Backtest option |
|---|---|---|
| Timeframe 2 min / 5 min | both | `--timeframe 2|5` |
| MA 1 type (SMA/EMA) and period, MA 2 type and period, any combination, custom periods | SMA 9, EMA 15 | `--ma1 sma:9 --ma2 ema:15` |
| Supertrend ATR length / factor | 10 / 3 | `--st-atr --st-factor` |
| RSI length | 21 | `--rsi-len` |
| Lot size | 65 (NIFTY) | `--lot-size`, `--lots` |
| 0-day expiry toggle | OFF | `--zero-dte` |

Chart drawing required on the dashboard: SMA, EMA, Supertrend and RSI; mark the crossover
candle, entry, SL, target and trailing SL (`chart.py` draws all of these). The 50% booking
needs an **even number of lots** in live trading (1 lot cannot be split); the backtest books
exactly half.

## Verification

- Synthetic data: entries only from 09:30 and only on setup candles with range ≤ 15, SL/target
  arithmetic, trail values = cost + multiples of 10, exits by 15:15, no overlapping trades,
  max 4 trades a day, no entry after 3 wins/losses in a row.
- `verify.py` on real data: SMA/EMA/RSI recomputed with pandas, Supertrend with a separate
  line-by-line Pine transcription: identical values and directions; setup candles identical
  (2m: CE 33 / PE 37, 5m: CE 20 / PE 33); 0 rule violations in all trades.
- Hand check (2m, 2 Nov 12:39 PE): SMA 9 23318.07 < EMA 15 23318.17 after being above,
  Supertrend down, RSI 43.49, range 13.9 → entry 23302.65, SL 23315.75, 1:3 23263.35 hit 12:55
  (SL to cost), low 23217.20 at 13:09 = 2 steps → SL cost − 20 = 23282.65, hit 14:17;
  P&L (39.30 + 20) / 2 = 29.65 points.
- Yahoo prices differ slightly from TradingView/broker feeds; a crossover decided by a few
  paise can differ.

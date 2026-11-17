# Intraday strategy backtests (NSE, yfinance)

| Strategy | Script | Timeframe |
|---|---|---|
| Neeraj – Kyle Algo + Liquidity Swings | `backtest.py` | 5m |
| LAXIT – SMA 20 High/Low + MACD | `laxit.py` | 5m (2m with `--interval 2m`) |

---

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
| CALL vs PUT | `--mode independent` (default): CALL and PUT are **separate trades** and can be open at the same time (like holding a call and a put option). A PUT signal does not close an open CALL; each closes only on its own zone, its 1% SL or 15:15. A new signal is ignored while a trade of the same side is open |
| Other modes | `--mode reverse`: one position, and an opposite signal reverses it. `--mode hold` (or `--no-reverse`): one position, and opposite signals are ignored until it closes |
| CALL exit | Next **RED (swing-high) Liquidity Swings zone** |
| PUT exit | Next **GREEN (swing-low) zone** |
| Exit timing, `--exit-at swing` (default) | Matches manual chart reading: exit at the **close of the swing candle** where the zone box starts, for the first zone whose swing candle is at or after the entry. ⚠️ **Hindsight:** a zone is only known 14 candles after its swing candle, so these exits can't be taken live and the results are overstated |
| Exit timing, `--exit-at confirm` | Tradable live: exit at the next candle's open after the zone **appears** (14 candles after the swing candle, `ta.pivothigh/pivotlow(14, 14)`) |
| Stop loss | 1% from entry, checked against each candle's high/low; fills at the stop (or at the open if price gaps through it) |
| Square-off | Any open position closes at **15:15** (close of the 15:10–15:15 candle) |
| No new trades | No entry on the candle ending 15:15: the last entry fills at the 15:05 open, so an entry signal candle must close by 15:05. Liquidity-zone exits still act up to the 15:10 open |
| Instrument | CALL = long stock, PUT = short stock. P&L is per share on the underlying, before costs unless `--cost-pct` is set |
| Kyle BUY/SELL labels | Not used |

### Notes on the indicator settings

* **Kyle Algo (Sensitivity 1.7, Keltner 11, ATR 10, Factor 1):** these inputs only drive the
  Supertrend BUY/SELL labels and the candle colours. The EMA ribbon has no inputs, so these
  settings **do not change any trade**. They are recorded in `backtest.py` for reference only.
* **Liquidity Swings (Lookback 14, Wick Extremity, Filter by Count, 0):** ported from the
  LuxAlgo source (`get_counts` / `set_zone`). A zone box is only **drawn** once a later
  candle trades back into the zone (count crosses above 0). Swings that price never
  revisits before the next swing are never drawn and are ignored for exits. A drawn
  zone can therefore appear more than 14 candles after its swing candle.
* List the zones drawn on a day, to compare with TradingView:
  `python backtest.py --zones 2026-11-13`
* Pivot ties: the pivot candle must be strictly higher (or lower) than the 14 candles to its
  left and at least equal to the 14 to its right.
* "Fully above or below the ribbon" uses a strict comparison of close against the highest or
  lowest of the 15 EMAs.

---

# LAXIT – Intraday Strategy (backtest)

```bash
python laxit.py                           # RELIANCE.NS 5m, last 5 complete sessions
python laxit.py --interval 2m             # same rules on 2-minute candles
python laxit.py --sessions 40 --cost-pct 0.05
python laxit.py --day 2026-11-13          # print one day's trades
python laxit.py --one-at-a-time           # no CALL/PUT overlap
```

Outputs go to `results_laxit/`. MACD follows the TradingView built-in source: EMA 12 − EMA 26
of close, signal = EMA 9 of MACD (EMAs seeded like Pine's `ta.ema`). A crossover is the
histogram crossing 0.

| Item | Implementation |
|---|---|
| Timeframe | 5-minute candles (`--interval 2m` for 2-minute) |
| Indicators | SMA 20 of High, SMA 20 of Low, MACD 12/26/9 on close |
| CALL setup candle | Green, **more than 50% of its body above SMA 20 High**, and a **bullish MACD crossover** (MACD crossing above its signal line) on this candle or the 2 candles before it, with MACD still above signal |
| PUT setup candle | Red, more than 50% of its body below SMA 20 Low, and a bearish crossover on this candle or the 2 before it, with MACD still below signal |
| Entry | **Next candle only**: CALL fills when price breaks above the setup high (at the open if it gaps above it). PUT fills on a break below the setup low |
| Trading time | Entry candle between 09:45 and 14:20 (last 5m entry candle 14:15–14:20). Trades already open are held until 15:15 |
| Stop loss | CALL: SMA 20 Low on the setup candle. PUT: SMA 20 High. Fixed until T1 |
| T1 | 1:1 of the initial risk: book **50%** and move SL to **cost** |
| Trail | After T1, at each candle close the SL follows SMA 20 Low (CALL) or SMA 20 High (PUT), only ever tightening and never past cost |
| Exit | SL / cost / trailing SL, otherwise squared off at 15:15 |
| Same candle hits SL and target | SL counted first (conservative) |
| CALL vs PUT | Independent trades, one open per side (`--one-at-a-time` allows a single position) |
| P&L | Per share: 50% at T1 + 50% at the final exit (100% at the SL if T1 was never reached) |
